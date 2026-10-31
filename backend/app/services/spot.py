"""Spot price polling with provider fallback, quota caps and market-hours awareness."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import EncryptionUnavailable
from app.logging_setup import log
from app.models import METALS, ApiCallLog, ProviderConfig, SpotPrice, User, utcnow
from app.providers.base import CATALOG, ProviderError, http_client
from app.providers.spot import SPOT_PROVIDERS
from app.services import providers as psvc


def market_open(now: dt.datetime | None = None) -> bool:
    """Precious-metals spot trades nearly 24h on weekdays: closed Fri 17:00 to Sun 18:00 New York time."""
    local = (now or utcnow()).astimezone(ZoneInfo(get_settings().timezone))
    wd, t = local.weekday(), local.time()
    if wd == 5:  # Saturday
        return False
    if wd == 4 and t >= dt.time(17, 0):
        return False
    if wd == 6 and t < dt.time(18, 0):
        return False
    return True


@dataclass
class PollOutcome:
    currency: str
    sources: dict[str, str] = field(default_factory=dict)  # metal -> provider that gave a current price
    old_metals: list[str] = field(default_factory=list)  # metals still without a current price
    skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.sources)

    @property
    def source(self) -> str | None:
        seen = list(dict.fromkeys(self.sources.values()))
        return ", ".join(seen) if seen else None


def poll_currencies(db: Session) -> list[str]:
    found = [c for (c,) in db.execute(select(distinct(User.base_currency)).where(User.is_active.is_(True)))]
    return found or ["USD"]


def _aware(t: dt.datetime | None) -> dt.datetime | None:
    return None if t is None else (t if t.tzinfo else t.replace(tzinfo=dt.UTC))


def is_stale(price_time: dt.datetime, now: dt.datetime, threshold: dt.timedelta, is_open: bool) -> bool:
    """Judged on when the market price was set, not when we fetched it.
    While markets are closed the Friday close stays current, so allow up to three days."""
    return now - price_time > (threshold if is_open else dt.timedelta(days=3))


def _threshold(db: Session) -> dt.timedelta:
    return dt.timedelta(minutes=int(psvc.get_system(db, "spot_stale_minutes") or 30))


def poll(
    db: Session,
    currencies: list[str] | None = None,
    *,
    force: bool = False,
    client: httpx.Client | None = None,
    now: dt.datetime | None = None,
) -> list[PollOutcome]:
    now = (now or utcnow()).astimezone(dt.UTC)
    is_open = market_open(now)
    if not force and not is_open and psvc.get_system(db, "spot_pause_weekends"):
        return [PollOutcome(c, skipped_reason="markets closed") for c in (currencies or poll_currencies(db))]
    own_client = client is None
    client = client or http_client()
    try:
        return [_poll_one(db, cur, client, now, is_open, force) for cur in (currencies or poll_currencies(db))]
    finally:
        if own_client:
            client.close()


def _pace_ok(db: Session, cfg: ProviderConfig, quota, now: dt.datetime) -> bool:
    """Spread a capped provider's requests over its period: at most one per (time left / requests left).
    Free calls (Test, usage checks) don't count, so pressing Test doesn't delay prices."""
    if quota is None:
        return True
    last = db.scalar(
        select(ApiCallLog.at)
        .where(ApiCallLog.provider_key == cfg.provider_key, ApiCallLog.cost > 0)
        .order_by(ApiCallLog.at.desc())
        .limit(1)
    )
    if last is None:
        return True
    remaining = quota.remaining(now)
    if remaining is None:
        return True
    gap = (_aware(quota.period(now).period_end) - now) / max(remaining, 1)
    return now - _aware(last) >= gap


def _last_source_time(db: Session, metal: str, currency: str) -> dt.datetime | None:
    row = db.scalar(
        select(SpotPrice)
        .where(SpotPrice.metal == metal, SpotPrice.currency == currency)
        .order_by(SpotPrice.fetched_at.desc(), SpotPrice.id.desc())
        .limit(1)
    )
    return None if row is None else _aware(row.source_timestamp or row.fetched_at)


def _poll_one(db: Session, currency: str, client: httpx.Client, now, is_open: bool, force: bool) -> PollOutcome:
    out = PollOutcome(currency)
    threshold = _threshold(db)
    pending = set(METALS)
    old_quotes: dict[str, tuple] = {}  # metal -> (quote, provider_key), the newest price that is too old to count
    configs = [psvc.get_config(db, k) for k, info in CATALOG.items() if info.kind == "spot"]
    configs = sorted((c for c in configs if c.enabled), key=lambda c: (c.priority, c.provider_key))
    for cfg in configs:
        if not pending:
            break
        info = CATALOG[cfg.provider_key]
        provider = SPOT_PROVIDERS[cfg.provider_key]
        try:
            key = psvc.api_key(cfg)
        except EncryptionUnavailable as exc:
            out.errors.append(f"{info.label}: {exc}")
            continue
        if info.needs_key and not key:
            continue
        if info.rate_limited and not is_open and not force:
            continue
        quota = psvc.quota_for(db, cfg)
        if quota is not None and not quota.can_spend(1, now):
            out.errors.append(f"{info.label}: monthly cap reached")
            psvc.log_call(db, cfg.provider_key, "spot", "skipped", context=currency, detail="quota cap reached")
            continue
        if not force and not _pace_ok(db, cfg, quota, now):
            # Not an error: the backup is rationed so its free requests last the whole month.
            continue
        with psvc.timed() as t:
            try:
                result = provider.fetch(client, currency, key)
            except ProviderError as exc:
                if quota is not None:
                    quota.record(exc.cost, now)
                psvc.mark_failure(cfg, str(exc))
                psvc.log_call(
                    db, cfg.provider_key, "spot", "error", context=currency, http_status=exc.http_status,
                    cost=exc.cost, detail=str(exc), at=now,
                )
                out.errors.append(f"{info.label}: {exc}")
                log.warning("spot_provider_failed", provider=cfg.provider_key, error=str(exc))
                continue
        if quota is not None:
            quota.record(result.cost, now)
        old_here: list[str] = []
        for q in result.quotes:
            if q.metal not in pending:
                continue
            price_time = _aware(q.source_timestamp) or now
            if is_stale(price_time, now, threshold, is_open):
                prev = old_quotes.get(q.metal)
                if prev is None or (_aware(prev[0].source_timestamp) or now) < price_time:
                    old_quotes[q.metal] = (q, cfg.provider_key)
                old_here.append(f"{q.metal} from {price_time:%Y-%m-%d %H:%M} UTC")
                continue
            _store(db, q, cfg.provider_key, now)
            pending.discard(q.metal)
            out.sources[q.metal] = cfg.provider_key
        detail = "; ".join(
            ([f"old prices: {', '.join(old_here)}"] if old_here else []) + result.problems
        ) or None
        for problem in result.problems:
            out.errors.append(f"{info.label}: {problem}")
        if old_here:
            out.errors.append(f"{info.label}: old prices for {', '.join(old_here)}")
        psvc.mark_success(cfg)
        psvc.log_call(
            db, cfg.provider_key, ",".join(result.endpoints) or "spot", "ok", context=currency, cost=result.cost,
            duration_ms=t["ms"], detail=detail, at=now,
        )
    # No current price anywhere: keep the newest old one so melt value still has a number,
    # flagged stale by its age. Store it once, not on every poll.
    for metal in sorted(pending):
        if metal in old_quotes:
            q, src = old_quotes[metal]
            last = _last_source_time(db, metal, currency)
            q_time = _aware(q.source_timestamp) or now
            if last is None or q_time > last:
                _store(db, q, src, now)
    out.old_metals = sorted(pending)
    db.commit()
    if not out.ok:
        log.error("spot_poll_failed", currency=currency, errors=out.errors)
    elif pending:
        log.warning("spot_prices_old", currency=currency, metals=out.old_metals)
    return out


def _store(db: Session, q, source: str, now: dt.datetime) -> None:
    db.add(
        SpotPrice(
            metal=q.metal,
            currency=q.currency,
            price_per_toz=q.price_per_toz,
            source=source,
            source_timestamp=q.source_timestamp,
            fetched_at=now,
        )
    )


@dataclass
class Latest:
    price: SpotPrice | None
    stale: bool

    @property
    def price_time(self) -> dt.datetime | None:
        if self.price is None:
            return None
        return _aware(self.price.source_timestamp or self.price.fetched_at)


def latest(db: Session, currency: str, now: dt.datetime | None = None) -> dict[str, Latest]:
    now = (now or utcnow()).astimezone(dt.UTC)
    threshold = _threshold(db)
    is_open = market_open(now)
    out: dict[str, Latest] = {}
    for metal in METALS:
        row = db.scalar(
            select(SpotPrice)
            .where(SpotPrice.metal == metal, SpotPrice.currency == currency)
            .order_by(SpotPrice.fetched_at.desc(), SpotPrice.id.desc())
            .limit(1)
        )
        if row is None:
            out[metal] = Latest(None, True)
            continue
        entry = Latest(row, False)
        entry.stale = is_stale(entry.price_time, now, threshold, is_open)
        out[metal] = entry
    return out


def spot_map(db: Session, currency: str) -> dict[str, "Decimal"]:  # noqa: F821
    return {m: l.price.price_per_toz for m, l in latest(db, currency).items() if l.price is not None}


def history(db: Session, metal: str, currency: str, since: dt.datetime) -> list[SpotPrice]:
    return list(
        db.scalars(
            select(SpotPrice)
            .where(SpotPrice.metal == metal, SpotPrice.currency == currency, SpotPrice.fetched_at >= since)
            .order_by(SpotPrice.fetched_at)
        )
    )


def ensure_spot_configs(db: Session) -> list[ProviderConfig]:
    return [psvc.get_config(db, k) for k, info in CATALOG.items() if info.kind == "spot"]
