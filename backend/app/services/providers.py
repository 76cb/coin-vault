"""Provider configuration rows, encrypted keys, call logging and system settings."""

from __future__ import annotations

import datetime as dt
import time
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto
from app.models import ApiCallLog, ProviderConfig, SystemSetting, utcnow
from app.providers.base import CATALOG, ProviderInfo
from app.services.quota import QuotaManager

SYSTEM_DEFAULTS: dict[str, object] = {
    "spot_poll_minutes": 15,
    "spot_stale_minutes": 30,
    "spot_pause_weekends": True,
    "backup_enabled": True,
    "backup_time": "03:15",  # local time (CV_TIMEZONE)
    "updates_enabled": True,  # weekly refresh of the PCGS and Numista values you've fetched
    "updates_day": "sun",
    "updates_time": "05:40",  # local time (CV_TIMEZONE)
}


def get_system(db: Session, key: str):
    row = db.get(SystemSetting, key)
    return row.value if row is not None else SYSTEM_DEFAULTS.get(key)


def set_system(db: Session, key: str, value) -> None:
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        row.value = value


def get_config(db: Session, key: str) -> ProviderConfig:
    info = CATALOG[key]
    cfg = db.scalar(select(ProviderConfig).where(ProviderConfig.provider_key == key))
    if cfg is None:
        cfg = ProviderConfig(
            provider_key=key,
            kind=info.kind,
            enabled=True,
            priority=info.default_priority,
            quota_cap=info.default_cap,
            settings={},
            consecutive_failures=0,
        )
        db.add(cfg)
        db.flush()
    return cfg


def api_key(cfg: ProviderConfig) -> str | None:
    if not cfg.api_key_encrypted:
        return None
    return crypto.decrypt(cfg.api_key_encrypted)


def set_api_key(cfg: ProviderConfig, value: str | None) -> None:
    if value:
        cfg.api_key_encrypted = crypto.encrypt(value)
        cfg.api_key_last4 = value[-4:]
    else:
        cfg.api_key_encrypted = None
        cfg.api_key_last4 = None
    cfg.last_error = None
    cfg.consecutive_failures = 0


def quota_for(db: Session, cfg: ProviderConfig) -> QuotaManager | None:
    info: ProviderInfo = CATALOG[cfg.provider_key]
    if not info.has_quota:
        return None
    return QuotaManager(db, cfg.provider_key, cfg.quota_cap, info.quota_period or "calendar_month")


def log_call(
    db: Session,
    provider_key: str,
    endpoint: str,
    status: str,
    *,
    context: str | None = None,
    http_status: int | None = None,
    cost: int = 0,
    duration_ms: int | None = None,
    detail: str | None = None,
    at: dt.datetime | None = None,
) -> None:
    db.add(
        ApiCallLog(
            **({"at": at} if at is not None else {}),
            provider_key=provider_key,
            endpoint=endpoint[:120],
            context=(context or None) and context[:200],
            status=status,
            http_status=http_status,
            cost=cost,
            duration_ms=duration_ms,
            detail=(detail or None) and detail[:1000],
        )
    )


@contextmanager
def timed():
    box = {"ms": 0}
    start = time.perf_counter()
    try:
        yield box
    finally:
        box["ms"] = int((time.perf_counter() - start) * 1000)


def mark_success(cfg: ProviderConfig) -> None:
    cfg.last_success_at = utcnow()
    cfg.consecutive_failures = 0


def mark_failure(cfg: ProviderConfig, message: str) -> None:
    cfg.last_error = message[:1000]
    cfg.last_error_at = utcnow()
    cfg.consecutive_failures = (cfg.consecutive_failures or 0) + 1
