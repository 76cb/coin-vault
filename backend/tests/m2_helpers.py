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
        self.metals_dev_body: dict | None = None
        self.soldcomps_usage: dict | None = None
        self.soldcomps_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{url.host}{url.path}")
        if url.host == "api.gold-api.com":
            if self.gold_api_status != 200:
                return httpx.Response(self.gold_api_status, text="upstream error")
            _, _, symbol, currency = url.path.split("/")
            body = self.gold_api_body or {
                "currency": currency,
                "currencySymbol": "$",
                "exchangeRate": 1,
                "name": symbol,
                "price": GOLD[symbol],
                "symbol": symbol,
                "updatedAt": "2026-10-28T15:00:00Z",
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
