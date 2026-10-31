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
Metal Sentinel https://metal-sentinel.com/openapi.json (checked 2026-10-31), through RapidAPI
    GET https://metal-sentinel.p.rapidapi.com/api/metal-quote?symbol=PT&currency=USD
        headers X-RapidAPI-Key, X-RapidAPI-Host: metal-sentinel.p.rapidapi.com
    -> {"ID", "results": [{"symbol","currency","ask","mid","bid",...,"timestamp" (Unix s),"unit" ("OUNCE"),
        "originalTime"}]}  or, with HTTP 200, {"error": "...", "errors": {...}}
    GET /api/market-status -> {"status": "open"|"closed", "next"}
    One request per call. RapidAPI quota headers (docs.rapidapi.com/v2.0.0/docs/response-headers):
    x-rate-limit-rapid-free-plans-hard-limit-{limit,remaining,reset} on free plans,
    x-ratelimit-requests-{limit,remaining,reset} otherwise; reset is seconds until the quota resets.
"""

from __future__ import annotations

import datetime as dt
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

    def cost_for(self, metals) -> int:
        return 0

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None = None, metals=None) -> SpotResult:
        quotes: list[SpotQuote] = []
        endpoints: list[str] = []
        problems: list[ProviderError] = []
        # One call per metal; a failure on one metal doesn't throw away the others.
        for metal, symbol in METAL_SYMBOLS.items():
            if metals is not None and metal not in metals:
                continue
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

    def cost_for(self, metals) -> int:
        return 1  # one call returns every metal

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None, metals=None) -> SpotResult:
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


METAL_SENTINEL_BASE = "https://metal-sentinel.p.rapidapi.com"
METAL_SENTINEL_HOST = "metal-sentinel.p.rapidapi.com"
METAL_SENTINEL_SYMBOLS = {"Au": "AU", "Ag": "AG", "Pt": "PT", "Pd": "PD"}


def rapidapi_usage(r: httpx.Response, now: dt.datetime | None = None) -> UsageInfo | None:
    """Monthly quota from RapidAPI's response headers; None when they're absent or describe a daily quota."""
    h = r.headers
    for prefix in ("x-rate-limit-rapid-free-plans-hard-limit-", "x-ratelimit-requests-"):
        limit, remaining, reset = (_int(h.get(prefix + k)) for k in ("limit", "remaining", "reset"))
        if limit is None or remaining is None:
            continue
        if reset is not None and reset < 2 * 86400 and prefix.startswith("x-ratelimit-requests"):
            return None  # a daily quota; our cap is monthly
        end = start = None
        if reset is not None:
            now = now or dt.datetime.now(dt.UTC)
            # reset counts down in seconds; round so every response in a period gives the same end
            end = dt.datetime.fromtimestamp(round((now.timestamp() + reset) / 600) * 600, dt.UTC)
            start = _sub_month(end)
        return UsageInfo(used=max(limit - remaining, 0), limit=limit, remaining=remaining, period_start=start, period_end=end)
    return None


def _sub_month(d: dt.datetime) -> dt.datetime:
    year, month = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return d.replace(year=year, month=month, day=day)


class MetalSentinel:
    key = "metal_sentinel"

    def cost_for(self, metals) -> int:
        return len(metals)  # one request per metal

    def _get(self, client: httpx.Client, api_key: str, path: str, params: dict | None = None) -> tuple[dict, httpx.Response]:
        try:
            r = client.get(
                METAL_SENTINEL_BASE + path,
                params=params,
                headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": METAL_SENTINEL_HOST},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__} calling Metal Sentinel", cost=0) from exc
        if r.status_code in (401, 403):
            # RapidAPI's answer for a wrong key or no subscription to this API
            raise ProviderError(f"Metal Sentinel refused the key (HTTP {r.status_code}); check you subscribed to its plan on RapidAPI", r.status_code, cost=0)
        if r.status_code == 429:
            raise ProviderError("Metal Sentinel: RapidAPI quota or rate limit reached (HTTP 429)", 429, cost=0)
        data = _json(r)
        if "error" in data:
            # validation and upstream feed errors come back as HTTP 200
            raise ProviderError(f"Metal Sentinel: {data['error']}", r.status_code, cost=1)
        if r.status_code != 200:
            raise ProviderError(f"Metal Sentinel returned HTTP {r.status_code}", r.status_code, cost=1)
        return data, r

    def fetch(self, client: httpx.Client, currency: str, api_key: str | None, metals=None) -> SpotResult:
        if not api_key:
            raise ProviderError("no API key set", cost=0)
        quotes: list[SpotQuote] = []
        problems: list[ProviderError] = []
        endpoints: list[str] = []
        usage = None
        cost = 0
        for metal, symbol in METAL_SENTINEL_SYMBOLS.items():
            if metals is not None and metal not in metals:
                continue
            endpoints.append(f"/api/metal-quote?symbol={symbol}")
            try:
                data, r = self._get(client, api_key, "/api/metal-quote", {"symbol": symbol, "currency": currency})
            except ProviderError as exc:
                cost += exc.cost
                problems.append(exc)
                if exc.http_status in (401, 403, 429):
                    break  # the rest would fail the same way
                continue
            cost += 1
            usage = rapidapi_usage(r) or usage
            try:
                quotes.append(self._quote(data, metal, symbol, currency))
            except ProviderError as exc:
                problems.append(exc)
        if not quotes:
            err = problems[0] if problems else ProviderError("Metal Sentinel returned no prices")
            err.cost = cost
            raise err
        return SpotResult(quotes=quotes, cost=cost, endpoints=endpoints, problems=[str(p) for p in problems], usage=usage)

    @staticmethod
    def _quote(data: dict, metal: str, symbol: str, currency: str) -> SpotQuote:
        results = data.get("results")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise ProviderError(f"Metal Sentinel: no result for {symbol}")
        q = results[0]
        if str(q.get("symbol", symbol)).upper() != symbol:
            raise ProviderError(f"Metal Sentinel answered for {q.get('symbol')} instead of {symbol}")
        if str(q.get("currency", currency)).upper() != currency.upper():
            raise ProviderError(f"Metal Sentinel answered in {q.get('currency')} instead of {currency}")
        if str(q.get("unit", "")).upper() != "OUNCE":
            raise ProviderError(f"Metal Sentinel priced {symbol} per {q.get('unit')!r}, not per troy ounce")
        mid = q.get("mid")
        if mid is None and q.get("bid") is not None and q.get("ask") is not None:
            mid = (Decimal(str(q["bid"])) + Decimal(str(q["ask"]))) / 2
        ts = None
        if isinstance(q.get("timestamp"), (int, float)):
            ts = dt.datetime.fromtimestamp(q["timestamp"], dt.UTC)
        else:
            ts = parse_ts(q.get("originalTime"))
        return SpotQuote(metal, currency, _decimal(mid), ts)

    def check(self, client: httpx.Client, api_key: str) -> tuple[str, UsageInfo | None]:
        """One request (it counts against the quota): market status, plus the quota headers."""
        data, r = self._get(client, api_key, "/api/market-status")
        status = data.get("status")
        msg = "Key accepted." + (f" Metal Sentinel says the market is {status}." if status in ("open", "closed") else "")
        return msg, rapidapi_usage(r)


SPOT_PROVIDERS = {p.key: p for p in (GoldApi(), MetalSentinel(), MetalsDev())}
