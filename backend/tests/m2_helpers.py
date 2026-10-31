"""Fake provider responses in each provider's documented format."""

from __future__ import annotations

import json

import httpx

GOLD = {"XAU": 4000.0, "XAG": 50.0, "XPT": 1500.0, "XPD": 1100.0}


class FakeProviders:
    """An httpx transport that answers like gold-api.com, Metals.Dev and SoldComps, and records every call."""

    def __init__(self):
        self.calls: list[str] = []
        self.gold_api_status = 200
        self.gold_api_body: dict | None = None
        self.gold_api_updated: dict[str, str] = {}  # symbol -> updatedAt, to simulate a price that stopped updating
        self.gold_api_fail: set[str] = set()  # symbols that return HTTP 500
        self.metals_dev_body: dict | None = None
        self.soldcomps_usage: dict | None = None
        self.ms_prices = {"AU": 4005.0, "AG": 50.1, "PT": 1439.0, "PD": 1001.0}
        self.ms_status = 200
        self.ms_body: dict | None = None  # overrides the metal-quote answer
        self.ms_used = 100  # requests used so far this month, reported in RapidAPI's headers
        self.soldcomps_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{url.host}{url.path}")
        if url.host == "api.gold-api.com":
            if self.gold_api_status != 200:
                return httpx.Response(self.gold_api_status, text="upstream error")
            _, _, symbol, currency = url.path.split("/")
            if symbol in self.gold_api_fail:
                return httpx.Response(500, text="upstream error")
            body = self.gold_api_body or {
                "currency": currency,
                "currencySymbol": "$",
                "exchangeRate": 1,
                "name": symbol,
                "price": GOLD[symbol],
                "symbol": symbol,
                "updatedAt": self.gold_api_updated.get(symbol, "2026-10-28T15:00:00Z"),
                "updatedAtReadable": "a few seconds ago",
            }
            return httpx.Response(200, json=body)
        if url.host == "api.metals.dev":
            if url.path == "/usage":
                return httpx.Response(
                    200, json={"status": "success", "timestamp": "2026-10-28T15:00:00Z", "plan": "Free", "total": 100, "used": 7, "remaining": 93}
                )
            body = self.metals_dev_body or {
                "status": "success",
                "currency": url.params.get("currency"),
                "unit": "toz",
                "metals": {"gold": 4010.5, "silver": 50.25, "platinum": 1490.0, "palladium": 1105.0, "copper": 0.3},
                "currencies": {},
                "timestamps": {"metal": "2026-10-28T15:00:01.000Z", "currency": "2026-10-28T15:00:00.000Z"},
            }
            return httpx.Response(200, json=body)
        if url.host == "metal-sentinel.p.rapidapi.com":
            if request.headers.get("X-RapidAPI-Host") != "metal-sentinel.p.rapidapi.com":
                return httpx.Response(400, json={"message": "missing host header"})
            if self.ms_status != 200:
                return httpx.Response(self.ms_status, json={"message": "You are not subscribed to this API."})
            self.ms_used += 1
            headers = {
                "x-rate-limit-rapid-free-plans-hard-limit-limit": "7500",
                "x-rate-limit-rapid-free-plans-hard-limit-remaining": str(7500 - self.ms_used),
                "x-rate-limit-rapid-free-plans-hard-limit-reset": "86400",
            }
            if url.path == "/api/market-status":
                return httpx.Response(200, json={"status": "open", "next": "2026-10-30T21:00:00Z"}, headers=headers)
            sym = url.params.get("symbol")
            body = self.ms_body or {
                "ID": 1793412613,
                "results": [{
                    "symbol": sym, "currency": url.params.get("currency"), "ask": self.ms_prices[sym] + 1,
                    "mid": self.ms_prices[sym], "bid": self.ms_prices[sym] - 1, "high": 0, "low": 0, "open": 0,
                    "close": 0, "timestamp": 1793199600, "change": 0, "changePercentage": 0, "unit": "OUNCE",
                    "originalTime": "2026-10-28T15:00:00Z", "extra": None,
                }],
            }
            return httpx.Response(200, json=body, headers=headers)
        if url.host == "api.sold-comps.com" and url.path == "/usage":
            if request.headers.get("Authorization") != "Bearer sc_testkey1234":
                return httpx.Response(401, json={"error": "invalid key"})
            body = self.soldcomps_usage or {
                "plan": "free",
                "plan_label": "Free",
                "usage": {"limit": 100, "used": 12, "remaining": 88, "period_start": "2026-10-14T00:00:00Z", "reset_at": "2026-11-14T00:00:00Z"},
                "rate_limit": {"rpm": 60, "remaining": 60, "reset": None},
                "credits": {"balance": 0},
            }
            return httpx.Response(self.soldcomps_status, content=json.dumps(body), headers={"content-type": "application/json"})
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))
