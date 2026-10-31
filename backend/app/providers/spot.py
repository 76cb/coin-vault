"""Spot price providers.

gold-api.com  https://gold-api.com/llms.txt
    GET https://api.gold-api.com/price/{symbol}/{currency}  (no key, no rate limit; cache 30 s)
    -> {"currency","price","symbol","updatedAt", ...}
    Symbols (GET /symbols): XAU, XAG, XPT, XPD, HG, BTC, ETH. Checked 2026-10-31: XAU and XAG were
    live, but XPT's updatedAt was 2026-09-17 and XPD's 2026-10-16, so updatedAt is checked on every
    quote and old ones are filled from the backup provider (see services/spot.py).
Metals.Dev    https://metals.dev/docs
    GET https://api.metals.dev/v1/latest?api_key=&currency=&unit=toz  (one call, all metals)
    -> {"status","currency","unit","metals":{"gold","silver","platinum","palladium",...},"timestamps":{"metal"}}
    GET https://api.metals.dev/usage?api_key=  -> {"status","plan","total","used","remaining"}
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import METAL_SYMBOLS, ProviderError, SpotQuote, SpotResult, UsageInfo, parse_ts

GOLD_API_BASE = "https://api.gold-api.com"
METALS_DEV_BASE = "https://api.metals.dev"
METALS_DEV_NAMES = {"Au": "gold", "Ag": "silver", "Pt": "platinum", "Pd": "palladium"}


def _decimal(value) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ProviderError(f"unexpected price value {value!r}") from exc
    if not d.is_finite() or d <= 0:
        raise ProviderError(f"unexpected price value {value!r}")
    return d.quantize(Decimal("0.0001"))


class GoldApi:
    key = "gold_api"

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None = None) -> SpotResult:
        quotes: list[SpotQuote] = []
        endpoints: list[str] = []
        problems: list[ProviderError] = []
        # One call per metal; a failure on one metal doesn't throw away the others.
        for metal, symbol in METAL_SYMBOLS.items():
            path = f"/price/{symbol}/{currency}"
            endpoints.append(path)
            try:
                quotes.append(self._one(client, path, metal, symbol, currency))
            except ProviderError as exc:
                problems.append(exc)
        if not quotes:
            raise problems[0]
        return SpotResult(quotes=quotes, cost=0, endpoints=endpoints, problems=[str(p) for p in problems])

    @staticmethod
    def _one(client: httpx.Client, path: str, metal: str, symbol: str, currency: str) -> SpotQuote:
        try:
            r = client.get(GOLD_API_BASE + path)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__} calling gold-api.com") from exc
        if r.status_code != 200:
            raise ProviderError(f"gold-api.com returned HTTP {r.status_code} for {symbol}", r.status_code)
        data = _json(r)
        if str(data.get("currency", currency)).upper() != currency.upper():
            raise ProviderError(f"gold-api.com answered in {data.get('currency')} instead of {currency}")
        return SpotQuote(metal, currency, _decimal(data.get("price")), parse_ts(data.get("updatedAt")))


class MetalsDev:
    key = "metals_dev"

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None) -> SpotResult:
        if not api_key:
            raise ProviderError("no API key set")
        try:
            r = client.get(
                f"{METALS_DEV_BASE}/v1/latest",
                params={"api_key": api_key, "currency": currency, "unit": "toz"},
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__} calling Metals.Dev") from exc
        data = _json(r)
        if data.get("status") != "success":
            code = data.get("error_code")
            # 1101 invalid key, 1203 quota exceeded: neither consumed a successful request.
            raise ProviderError(f"Metals.Dev error {code}: {data.get('error_message', 'unknown error')}", r.status_code)
        metals = data.get("metals") or {}
        ts = parse_ts((data.get("timestamps") or {}).get("metal"))
        quotes = [
            SpotQuote(metal, currency, _decimal(metals.get(name)), ts) for metal, name in METALS_DEV_NAMES.items()
        ]
        return SpotResult(quotes=quotes, cost=1, endpoints=["/v1/latest"])

    def usage(self, client: httpx.Client, api_key: str) -> UsageInfo:
        try:
            r = client.get(f"{METALS_DEV_BASE}/usage", params={"api_key": api_key})
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__} calling Metals.Dev") from exc
        data = _json(r)
        if data.get("status") != "success":
            raise ProviderError(f"Metals.Dev error {data.get('error_code')}: {data.get('error_message', '')}", r.status_code)
        return UsageInfo(
            used=int(data.get("used", 0)),
            limit=_int(data.get("total")),
            remaining=_int(data.get("remaining")),
            period_start=None,
            period_end=None,
            plan=data.get("plan"),
        )


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError as exc:
        raise ProviderError(f"non-JSON response (HTTP {r.status_code})", r.status_code) from exc
    if not isinstance(data, dict):
        raise ProviderError("unexpected response shape", r.status_code)
    return data


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


SPOT_PROVIDERS = {p.key: p for p in (GoldApi(), MetalsDev())}
