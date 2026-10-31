"""Provider interfaces and the catalogue of providers the app knows about."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

import httpx

from app import __version__
from app.config import get_settings

METAL_SYMBOLS = {"Au": "XAU", "Ag": "XAG", "Pt": "XPT", "Pd": "XPD"}


class ProviderError(Exception):
    """A provider call failed. `cost` is how many quota requests it used (failed calls are usually free)."""

    def __init__(self, message: str, http_status: int | None = None, cost: int = 0):
        super().__init__(message)
        self.http_status = http_status
        self.cost = cost


class QuotaExhausted(ProviderError):
    pass


@dataclass
class SpotQuote:
    metal: str
    currency: str
    price_per_toz: Decimal
    source_timestamp: dt.datetime | None


@dataclass
class SpotResult:
    quotes: list[SpotQuote]
    cost: int  # quota requests used
    endpoints: list[str] = field(default_factory=list)


@dataclass
class UsageInfo:
    used: int
    limit: int | None
    remaining: int | None
    period_start: dt.datetime | None
    period_end: dt.datetime | None
    plan: str | None = None


class SpotProvider(Protocol):
    key: str

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None) -> SpotResult: ...


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    kind: str
    label: str
    needs_key: bool
    has_quota: bool
    quota_period: str | None  # "calendar_month", "billing_cycle" or None
    default_cap: int | None
    default_priority: int
    rate_limited: bool  # skip polling outside market hours when true
    docs_url: str
    key_url: str | None
    note: str
    available_from: int  # milestone in which it is used


CATALOG: dict[str, ProviderInfo] = {
    "gold_api": ProviderInfo(
        key="gold_api",
        kind="spot",
        label="gold-api.com",
        needs_key=False,
        has_quota=False,
        quota_period=None,
        default_cap=None,
        default_priority=10,
        rate_limited=False,
        docs_url="https://gold-api.com/docs",
        key_url=None,
        note="Free live prices, no key, updated every 30 seconds. Primary spot source.",
        available_from=2,
    ),
    "metals_dev": ProviderInfo(
        key="metals_dev",
        kind="spot",
        label="Metals.Dev",
        needs_key=True,
        has_quota=True,
        quota_period="calendar_month",
        default_cap=90,
        default_priority=20,
        rate_limited=True,
        docs_url="https://metals.dev/docs",
        key_url="https://metals.dev/pricing",
        note="Backup spot source. Free plan: 100 requests a month, so it is used only when gold-api.com fails.",
        available_from=2,
    ),
    "soldcomps": ProviderInfo(
        key="soldcomps",
        kind="comps",
        label="SoldComps (eBay sold)",
        needs_key=True,
        has_quota=True,
        quota_period="billing_cycle",
        default_cap=90,
        default_priority=10,
        rate_limited=False,
        docs_url="https://sold-comps.com/docs",
        key_url="https://sold-comps.com/dashboard/api-keys",
        note="eBay sold listings for market value. Free plan: 100 requests a month. Comps searches arrive in Milestone 4; the key and usage work now.",
        available_from=4,
    ),
}


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=get_settings().http_timeout_seconds,
        headers={"User-Agent": f"CoinVault/{__version__} (self-hosted)"},
        follow_redirects=False,
    )


def parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
