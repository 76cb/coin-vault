"""SoldComps account endpoints (https://sold-comps.com/docs, openapi.json).

GET https://api.sold-comps.com/usage  Authorization: Bearer sc_...
    Free: does not count against the quota.
    -> {"plan","plan_label","usage":{"limit","used","remaining","period_start","reset_at"},
        "rate_limit":{...},"credits":{"balance"}}
GET https://api.sold-comps.com/v1/scrape?keyword=&sold=true&...  Authorization: Bearer sc_...
    1 request per page. -> {"keyword","page","totalItems","totalResults","hasNextPage","items":[{
        "itemId","url","title","thumbnailUrl","condition","buyingFormat","bidCount","endedAt" (YYYY-MM-DD),
        "soldPrice","soldCurrency","shippingPrice","shippingType","totalPrice","bestOfferAccepted",
        "listingType", ...}]}
    Prices are plain decimal strings; currency is separate.
    Errors: 400/500/503 {"error","code","detail"}; 401 {"error"}; 429 {"code": "rate_limited"|"quota_exceeded", ...}.
    Usage headers on 200 and quota 429: X-Usage-Limit, X-Usage-Used, X-Usage-Remaining, X-Usage-Reset (ISO 8601).
(openapi.json checked 2026-10-31.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import ProviderError, UsageInfo, parse_ts, sub_month

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


@dataclass
class Listing:
    item_id: str
    title: str | None
    url: str
    thumbnail_url: str | None
    condition: str | None
    buying_format: str | None
    ended_at: str | None
    sold_price: Decimal | None
    shipping_price: Decimal | None
    total_price: Decimal | None
    currency: str | None
    best_offer: bool


@dataclass
class SearchResult:
    keyword: str
    total_results: str | None
    has_next_page: bool
    listings: list[Listing] = field(default_factory=list)
    usage: UsageInfo | None = None


def _dec(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d >= 0 else None


def usage_from_headers(r: httpx.Response) -> UsageInfo | None:
    h = r.headers
    limit, used, remaining = _int(h.get("x-usage-limit")), _int(h.get("x-usage-used")), _int(h.get("x-usage-remaining"))
    if limit is None or used is None:
        return None
    end = parse_ts(h.get("x-usage-reset"))
    start = sub_month(end) if end is not None else None
    return UsageInfo(used=used, limit=limit, remaining=remaining, period_start=start, period_end=end)


def search_sold(
    client: httpx.Client,
    api_key: str,
    keyword: str,
    *,
    sold_after: str | None = None,
    item_condition: str = "any",
    exact_match: bool = True,
    ebay_site: str = "ebay.com",
) -> SearchResult:
    """One page of eBay sold listings, newest first. Costs one SoldComps request."""
    params = {
        "keyword": keyword,
        "sold": "true",
        "sortOrder": "endedRecently",
        "ebaySite": ebay_site,
        "itemCondition": item_condition,
        "exactMatch": "true" if exact_match else "false",
        "count": "60",
    }
    if sold_after:
        params["soldAfter"] = sold_after
    try:
        r = client.get(f"{BASE}/v1/scrape", params=params, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        raise ProviderError(f"{type(exc).__name__} calling SoldComps") from exc
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if r.status_code == 401:
        raise ProviderError("SoldComps rejected the API key (HTTP 401)", 401)
    if r.status_code == 429:
        if data.get("code") == "quota_exceeded":
            err = ProviderError(f"SoldComps monthly quota used up; it resets {data.get('reset_at', 'next period')}", 429)
        else:
            err = ProviderError(f"SoldComps rate limit; try again in {data.get('retry_after', 60)} seconds", 429)
        raise err
    if r.status_code != 200:
        msg = data.get("error") or f"HTTP {r.status_code}"
        raise ProviderError(f"SoldComps: {msg}", r.status_code)
    listings = []
    for it in data.get("items") or []:
        if not isinstance(it, dict) or it.get("listingType", "sold") != "sold":
            continue
        listings.append(
            Listing(
                item_id=str(it.get("itemId") or ""),
                title=it.get("title"),
                url=str(it.get("url") or ""),
                thumbnail_url=it.get("thumbnailUrl"),
                condition=it.get("condition"),
                buying_format=it.get("buyingFormat"),
                ended_at=it.get("endedAt"),
                sold_price=_dec(it.get("soldPrice")),
                shipping_price=_dec(it.get("shippingPrice")),
                total_price=_dec(it.get("totalPrice")),
                currency=it.get("soldCurrency"),
                best_offer=bool(it.get("bestOfferAccepted")),
            )
        )
    return SearchResult(
        keyword=str(data.get("keyword") or keyword),
        total_results=data.get("totalResults"),
        has_next_page=bool(data.get("hasNextPage")),
        listings=listings,
        usage=usage_from_headers(r),
    )
