"""SoldComps account endpoints (https://sold-comps.com/docs, openapi.json).

GET https://api.sold-comps.com/usage  Authorization: Bearer sc_...
    Free: does not count against the quota.
    -> {"plan","plan_label","usage":{"limit","used","remaining","period_start","reset_at"},
        "rate_limit":{...},"credits":{"balance"}}
Comps searches (/v1/scrape) are added in Milestone 4.
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderError, UsageInfo, parse_ts

BASE = "https://api.sold-comps.com"


def usage(client: httpx.Client, api_key: str) -> UsageInfo:
    try:
        r = client.get(f"{BASE}/usage", headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        raise ProviderError(f"{type(exc).__name__} calling SoldComps") from exc
    if r.status_code == 401:
        raise ProviderError("SoldComps rejected the API key (HTTP 401)", 401)
    if r.status_code != 200:
        raise ProviderError(f"SoldComps returned HTTP {r.status_code}", r.status_code)
    try:
        data = r.json()
        u = data["usage"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ProviderError("unexpected SoldComps usage response", r.status_code) from exc
    return UsageInfo(
        used=int(u.get("used", 0)),
        limit=_int(u.get("limit")),
        remaining=_int(u.get("remaining")),
        period_start=parse_ts(u.get("period_start")),
        period_end=parse_ts(u.get("reset_at")),
        plan=data.get("plan_label") or data.get("plan"),
    )


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
