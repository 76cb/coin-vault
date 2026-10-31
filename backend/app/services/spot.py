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
from app.models import METALS, ProviderConfig, SpotPrice, User, utcnow
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
    source: str | None = None
    skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.source is not None


def poll_currencies(db: Session) -> list[str]:
    found = [c for (c,) in db.execute(select(distinct(User.base_currency)).where(User.is_active.is_(True)))]
    return found or ["USD"]


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


def _poll_one(db: Session, currency: str, client: httpx.Client, now, is_open: bool, force: bool) -> PollOutcome:
    out = PollOutcome(currency)
    configs = [psvc.get_config(db, k) for k, info in CATALOG.items() if info.kind == "spot"]
    configs = sorted((c for c in configs if c.enabled), key=lambda c: (c.priority, c.provider_key))
    for cfg in configs:
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
        with psvc.timed() as t:
            try:
                result = provider.fetch(client, currency, key)
            except ProviderError as exc:
                if quota is not None:
                    quota.record(exc.cost, now)
                psvc.mark_failure(cfg, str(exc))
                psvc.log_call(
                    db, cfg.provider_key, "spot", "error", context=currency, http_status=exc.http_status,
                    cost=exc.cost, detail=str(exc),
                )
                out.errors.append(f"{info.label}: {exc}")
                log.warning("spot_provider_failed", provider=cfg.provider_key, error=str(exc))
                continue
        if quota is not None:
            quota.record(result.cost, now)
        for q in result.quotes:
            db.add(
                SpotPrice(
                    metal=q.metal,
                    currency=q.currency,
                    price_per_toz=q.price_per_toz,
                    source=cfg.provider_key,
                    source_timestamp=q.source_timestamp,
                    fetched_at=now,
                )
            )
        psvc.mark_success(cfg)
        psvc.log_call(
            db, cfg.provider_key, ",".join(result.endpoints) or "spot", "ok", context=currency, cost=result.cost,
            duration_ms=t["ms"],
        )
        out.source = cfg.provider_key
        break
    db.commit()
    if not out.ok:
        log.error("spot_poll_failed", currency=currency, errors=out.errors)
    return out


@dataclass
class Latest:
    price: SpotPrice | None
    stale: bool


def latest(db: Session, currency: str, now: dt.datetime | None = None) -> dict[str, Latest]:
    now = (now or utcnow()).astimezone(dt.UTC)
    threshold = dt.timedelta(minutes=int(psvc.get_system(db, "spot_stale_minutes") or 30))
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
        fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=dt.UTC)
        # When markets are closed, the last price is still current until they reopen.
        stale = (now - fetched > threshold) if is_open else (now - fetched > dt.timedelta(days=3))
        out[metal] = Latest(row, stale)
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
