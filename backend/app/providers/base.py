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
    problems: list[str] = field(default_factory=list)  # per-metal failures when others succeeded
    usage: "UsageInfo | None" = None  # quota figures the provider reported alongside the prices


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

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None, metals: list[str] | None = None) -> SpotResult: ...

    def cost_for(self, metals: list[str]) -> int:
        """Quota requests a fetch of these metals will use."""
        ...


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
        note="Free, no key. Primary source: gold and silver are live. Its platinum and palladium prices had stopped updating when checked on Oct 31, 2026 (platinum last Sep 17, palladium Oct 16), so every price's own timestamp is checked "
        "and out-of-date ones come from a backup (Metal Sentinel, then Metals.Dev) instead.",
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
        note="Second backup, after Metal Sentinel. Free plan: 100 requests a month. It is only "
        "called for metals gold-api.com can't supply current prices for, and calls are spread evenly through the month "
        "(about one every 8 hours with a cap of 90) so the plan lasts.",
        available_from=2,
    ),
    "metal_sentinel": ProviderInfo(
        key="metal_sentinel",
        kind="spot",
        label="Metal Sentinel (RapidAPI)",
        needs_key=True,
        has_quota=True,
        quota_period="billing_cycle",
        default_cap=7000,
        default_priority=15,
        rate_limited=True,
        docs_url="https://metal-sentinel.com/endpoints",
        key_url="https://rapidapi.com/ghostsvos/api/metal-sentinel/pricing",
        note="Live platinum and palladium (updated every 15 seconds). Free RapidAPI plan: 7,500 requests a month, one "
        "request per metal. Only called for metals gold-api.com can't supply current prices for, paced to last the "
        "month; RapidAPI's own usage figures are read from each response. Use your RapidAPI application key.",
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
