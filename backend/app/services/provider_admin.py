"""Provider settings shown in the UI: status, key tests and usage reconciliation."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import EncryptionUnavailable
from app.logging_setup import log
from app.models import ApiCallLog, ProviderConfig, utcnow
from app.providers import soldcomps
from app.providers.base import CATALOG, ProviderError, UsageInfo, http_client
from app.providers.spot import SPOT_PROVIDERS, MetalsDev
from app.services import providers as psvc


@dataclass
class CheckResult:
    ok: bool
    message: str
    usage: UsageInfo | None = None


def fetch_usage(cfg: ProviderConfig, key: str, client: httpx.Client) -> UsageInfo | None:
    if cfg.provider_key == "metals_dev":
        return MetalsDev().usage(client, key)
    if cfg.provider_key == "soldcomps":
        return soldcomps.usage(client, key)
    return None


METAL_NAMES = {"Au": "Gold", "Ag": "Silver", "Pt": "Platinum", "Pd": "Palladium"}


def _describe_quotes(result, currency: str) -> str:
    """One line per metal with the price and how old the provider says it is."""
    now = utcnow()
    parts, old = [], []
    for q in result.quotes:
        ts = q.source_timestamp
        age = (now - ts) if ts else None
        when = "time not given" if ts is None else ("live" if age < dt.timedelta(hours=1) else f"last updated {ts:%b %-d}")
        parts.append(f"{METAL_NAMES.get(q.metal, q.metal)} {q.price_per_toz.normalize():,f} {currency} ({when})")
        if age is not None and age > dt.timedelta(days=3):
            old.append(METAL_NAMES.get(q.metal, q.metal).lower())
    msg = "Working. " + "; ".join(parts) + "."
    if result.problems:
        msg += " Failed: " + "; ".join(result.problems) + "."
    if old:
        msg += f" The {' and '.join(old)} prices here are old, so the backup provider supplies them when it has a key."
    return msg


def check_provider(db: Session, cfg: ProviderConfig, currency: str, client: httpx.Client | None = None) -> CheckResult:
    info = CATALOG[cfg.provider_key]
    own = client is None
    client = client or http_client()
    try:
        try:
            key = psvc.api_key(cfg)
        except EncryptionUnavailable as exc:
            return CheckResult(False, str(exc))
        if info.needs_key and not key:
            return CheckResult(False, "No API key saved yet.")
        with psvc.timed() as t:
            try:
                if cfg.provider_key == "gold_api":
                    usage = None
                    message = _describe_quotes(SPOT_PROVIDERS["gold_api"].fetch(client, currency), currency)
                else:
                    usage = fetch_usage(cfg, key, client)
                    message = "Key accepted."
                    if usage is not None and usage.limit is not None:
                        message += f" {usage.used} of {usage.limit} requests used this period."
            except ProviderError as exc:
                psvc.mark_failure(cfg, str(exc))
                psvc.log_call(db, cfg.provider_key, "test", "error", http_status=exc.http_status, detail=str(exc))
                db.commit()
                return CheckResult(False, str(exc))
        psvc.log_call(db, cfg.provider_key, "test", "ok", cost=0, duration_ms=t["ms"])
        psvc.mark_success(cfg)
        cfg.last_error = None
        if usage is not None:
            quota = psvc.quota_for(db, cfg)
            if quota is not None:
                quota.sync(usage)
        db.commit()
        return CheckResult(True, message, usage)
    finally:
        if own:
            client.close()


def sync_all_usage(db: Session) -> None:
    """Daily job: adopt each provider's own usage counts (these calls are free)."""
    with http_client() as client:
        for key, info in CATALOG.items():
            if not info.has_quota:
                continue
            cfg = psvc.get_config(db, key)
            try:
                api_key = psvc.api_key(cfg)
            except EncryptionUnavailable:
                continue
            if not api_key or not cfg.enabled:
                continue
            try:
                usage = fetch_usage(cfg, api_key, client)
            except ProviderError as exc:
                log.warning("usage_sync_failed", provider=key, error=str(exc))
                psvc.log_call(db, key, "usage", "error", http_status=exc.http_status, detail=str(exc))
                continue
            quota = psvc.quota_for(db, cfg)
            if usage is not None and quota is not None:
                row = quota.sync(usage)
                psvc.log_call(db, key, "usage", "ok", detail=f"provider reports {usage.used}/{usage.limit}")
                log.info("usage_synced", provider=key, used=row.used, limit=row.provider_limit)
        db.commit()


def daily_counts(db: Session, provider_key: str, days: int = 31) -> list[dict]:
    since = utcnow() - dt.timedelta(days=days)
    rows = db.scalars(
        select(ApiCallLog).where(ApiCallLog.provider_key == provider_key, ApiCallLog.at >= since).order_by(ApiCallLog.at)
    )
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "calls": 0, "errors": 0})
    for r in rows:
        at = r.at if r.at.tzinfo else r.at.replace(tzinfo=dt.UTC)
        day = at.date().isoformat()
        per_day[day]["calls"] += 1
        per_day[day]["requests"] += r.cost or 0
        if r.status == "error":
            per_day[day]["errors"] += 1
    return [{"date": d, **v} for d, v in sorted(per_day.items())]
