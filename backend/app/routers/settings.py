"""App settings and external provider settings (API keys, caps, usage)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import scheduler
from app.config import get_settings
from app.crypto import EncryptionUnavailable
from app.db import get_db
from app.deps import Principal, require_session
from app.models import ApiCallLog
from app.providers.base import CATALOG
from app.services import provider_admin
from app.services import providers as psvc

router = APIRouter(prefix="/settings", tags=["settings"])

# Currencies every spot provider supports (gold-api.com's list, docs checked 2026-10-30).
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "HKD", "SGD", "SEK", "NOK", "DKK", "NZD",
              "MXN", "INR", "BRL", "ZAR", "KRW"]


class SettingsOut(BaseModel):
    base_currency: str
    currencies: list[str]
    spot_poll_minutes: int
    spot_stale_minutes: int
    spot_pause_weekends: bool
    encryption_ready: bool
    scheduler_running: bool


class SettingsPatch(BaseModel):
    base_currency: str | None = None
    spot_poll_minutes: int | None = Field(default=None, ge=5, le=1440)
    spot_stale_minutes: int | None = Field(default=None, ge=5, le=10080)
    spot_pause_weekends: bool | None = None


def _settings_out(db: Session, principal: Principal) -> SettingsOut:
    return SettingsOut(
        base_currency=principal.user.base_currency,
        currencies=CURRENCIES,
        spot_poll_minutes=int(psvc.get_system(db, "spot_poll_minutes")),
        spot_stale_minutes=int(psvc.get_system(db, "spot_stale_minutes")),
        spot_pause_weekends=bool(psvc.get_system(db, "spot_pause_weekends")),
        encryption_ready=bool(get_settings().encryption_key),
        scheduler_running=scheduler.running(),
    )


@router.get("", response_model=SettingsOut)
def get_app_settings(principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    return _settings_out(db, principal)


@router.patch("", response_model=SettingsOut)
def patch_app_settings(body: SettingsPatch, principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "base_currency" in data and data["base_currency"]:
        cur = data["base_currency"].upper()
        if cur not in CURRENCIES:
            raise HTTPException(422, f"Currency must be one of {', '.join(CURRENCIES)}")
        principal.user.base_currency = cur
    for key in ("spot_poll_minutes", "spot_stale_minutes", "spot_pause_weekends"):
        if data.get(key) is not None:
            psvc.set_system(db, key, data[key])
    db.commit()
    if data.get("spot_poll_minutes"):
        scheduler.reschedule_spot(int(data["spot_poll_minutes"]))
    return _settings_out(db, principal)


class UsageOut(BaseModel):
    used: int
    cap: int | None
    provider_limit: int | None
    provider_used: int | None
    remaining: int | None
    period_start: dt.datetime
    period_end: dt.datetime
    synced_at: dt.datetime | None


class ProviderOut(BaseModel):
    key: str
    label: str
    kind: str
    note: str
    docs_url: str
    key_url: str | None
    available_from: int
    needs_key: bool
    key_set: bool
    key_last4: str | None
    enabled: bool
    priority: int
    quota_cap: int | None
    quota_period: str | None
    usage: UsageOut | None
    last_success_at: dt.datetime | None
    last_error: str | None
    last_error_at: dt.datetime | None
    consecutive_failures: int


class ProviderPatch(BaseModel):
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)
    quota_cap: int | None = Field(default=None, ge=0, le=10_000_000)


def _provider_out(db: Session, key: str) -> ProviderOut:
    info = CATALOG[key]
    cfg = psvc.get_config(db, key)
    usage = None
    quota = psvc.quota_for(db, cfg)
    if quota is not None:
        p = quota.period()
        usage = UsageOut(
            used=p.used,
            cap=cfg.quota_cap,
            provider_limit=p.provider_limit,
            provider_used=p.provider_used,
            remaining=quota.remaining(),
            period_start=p.period_start,
            period_end=p.period_end,
            synced_at=p.synced_at,
        )
    return ProviderOut(
        key=key,
        label=info.label,
        kind=info.kind,
        note=info.note,
        docs_url=info.docs_url,
        key_url=info.key_url,
        available_from=info.available_from,
        needs_key=info.needs_key,
        key_set=bool(cfg.api_key_encrypted),
        key_last4=cfg.api_key_last4,
        enabled=cfg.enabled,
        priority=cfg.priority,
        quota_cap=cfg.quota_cap,
        quota_period=info.quota_period,
        usage=usage,
        last_success_at=cfg.last_success_at,
        last_error=cfg.last_error,
        last_error_at=cfg.last_error_at,
        consecutive_failures=cfg.consecutive_failures or 0,
    )


def _known(key: str) -> None:
    if key not in CATALOG:
        raise HTTPException(404, "Unknown provider")


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(_: Principal = Depends(require_session), db: Session = Depends(get_db)):
    out = [_provider_out(db, k) for k in CATALOG]
    db.commit()  # persists default rows and periods created on first view
    return out


@router.put("/providers/{key}", response_model=ProviderOut)
def update_provider(key: str, body: ProviderPatch, _: Principal = Depends(require_session), db: Session = Depends(get_db)):
    """Send `api_key` to set or replace the key, or `"api_key": null` to remove it. The key is never returned."""
    _known(key)
    cfg = psvc.get_config(db, key)
    data = body.model_dump(exclude_unset=True)
    if "api_key" in data:
        if not CATALOG[key].needs_key:
            raise HTTPException(422, f"{CATALOG[key].label} does not use an API key")
        try:
            psvc.set_api_key(cfg, (data["api_key"] or "").strip() or None)
        except EncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
    for field in ("enabled", "priority", "quota_cap"):
        if data.get(field) is not None:
            setattr(cfg, field, data[field])
    db.commit()
    return _provider_out(db, key)


class TestOut(BaseModel):
    ok: bool
    message: str
    provider: ProviderOut


@router.post("/providers/{key}/test", response_model=TestOut)
def test_provider(key: str, principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    """Checks the key with a call that does not count against the quota (usage endpoints, or one free price)."""
    _known(key)
    cfg = psvc.get_config(db, key)
    result = provider_admin.check_provider(db, cfg, principal.user.base_currency)
    return TestOut(ok=result.ok, message=result.message, provider=_provider_out(db, key))


class DayCount(BaseModel):
    date: str
    requests: int
    calls: int
    errors: int


class CallOut(BaseModel):
    at: dt.datetime
    endpoint: str
    context: str | None
    status: str
    http_status: int | None
    cost: int
    duration_ms: int | None
    detail: str | None


class UsageHistoryOut(BaseModel):
    provider: ProviderOut
    days: list[DayCount]


@router.get("/providers/{key}/usage", response_model=UsageHistoryOut)
def provider_usage(key: str, _: Principal = Depends(require_session), db: Session = Depends(get_db)):
    _known(key)
    return UsageHistoryOut(provider=_provider_out(db, key), days=[DayCount(**d) for d in provider_admin.daily_counts(db, key)])


@router.get("/providers/{key}/calls", response_model=list[CallOut])
def provider_calls(
    key: str,
    limit: int = Query(default=50, ge=1, le=500),
    _: Principal = Depends(require_session),
    db: Session = Depends(get_db),
):
    _known(key)
    rows = db.scalars(
        select(ApiCallLog).where(ApiCallLog.provider_key == key).order_by(ApiCallLog.at.desc(), ApiCallLog.id.desc()).limit(limit)
    )
    return [CallOut.model_validate(r, from_attributes=True) for r in rows]
