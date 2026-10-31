"""Fake provider responses in each provider's documented format."""

from __future__ import annotations

import datetime as dt
import json

import httpx


def _recent(at: dt.datetime | None = None) -> dt.datetime:
    """The time providers stamp their prices with: the given moment, or an hour before now (never 'out of date')."""
    t = at or (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1))
    return t.astimezone(dt.UTC).replace(microsecond=0)


def _iso(at: dt.datetime | None = None) -> str:
    return _recent(at).strftime("%Y-%m-%dT%H:%M:%SZ")

GOLD = {"XAU": 4000.0, "XAG": 50.0, "XPT": 1500.0, "XPD": 1100.0}


class FakeProviders:
    """An httpx transport that answers like gold-api.com, Metals.Dev and SoldComps, and records every call."""

    def __init__(self, stamp: dt.datetime | None = None):
        self.stamp = stamp  # tests with a fixed "now" give the provider time to match it
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
        self.soldcomps_scrape_status = 200
        self.pcgs_certs = {"32573628": {
            "PCGSNo": "539704", "Name": "2015-S 25C Bombay Hook NP, Silver", "Year": 2015, "Denomination": "25C",
            "Mintage": "", "MintMark": "S", "MintLocation": "San Francisco", "MetalContent": "90% Silver, 10% Copper",
            "Diameter": 24.3, "Edge": "Reeded", "Weight": 6.25, "Country": "United States", "Grade": "PR70",
            "Designation": "DCAM", "PriceGuideValue": 45.0, "Population": 1203, "PopHigher": 0,
            "CoinFactsLink": "https://www.pcgs.com/coinfacts/coin/539704", "Designer": "", "CoinFactsNotes": "",
            "Images": [{"Thumbnail": "https://images.pcgs.com/t.jpg", "Fullsize": "https://images.pcgs.com/f.jpg"}],
            "MajorVariety": "", "MinorVariety": "", "DieVariety": "", "AuctionList": [], "SeriesName": "America the Beautiful Quarters",
            "Category": "Washington Quarters", "HasTrueViewImage": False, "ImageReady": True, "IsNFCSecure": False}}
        self.numista_types = {
            # the spec's own example for N# 420, plus a silver dollar with two issues
            420: {"id": 420, "url": "https://en.numista.com/420", "title": "5 Cents - Victoria",
                  "issuer": {"code": "canada", "name": "Canada"}, "min_year": 1858, "max_year": 1901,
                  "value": {"text": "5 Cents", "numeric_value": 0.05, "currency": {"id": 44, "name": "Canadian dollar"}},
                  "composition": {"text": "Silver (.925) (.925 silver .075 copper)"}, "weight": 1.167, "size": 15.494,
                  "obverse": {"thumbnail": "https://en.numista.com/catalogue/photos/canada/1009-180.jpg"},
                  "reverse": {"thumbnail": "https://en.numista.com/catalogue/photos/canada/1010-180.jpg"},
                  "references": [{"catalogue": {"id": 3, "code": "KM"}, "number": "2"}, {"catalogue": {"id": 24, "code": "Schön"}, "number": "2"}]},
        }
        self.numista_issues = {420: [
            {"id": 9001, "is_dated": True, "year": 1858, "gregorian_year": 1858, "mintage": 1500000},
            {"id": 9002, "is_dated": True, "year": 1870, "gregorian_year": 1870, "mintage": 2800000},
            {"id": 9003, "is_dated": True, "year": 1870, "gregorian_year": 1870, "mint_letter": "H", "mintage": 100000},
        ]}
        self.numista_prices = {9001: [{"grade": "f", "price": 18}, {"grade": "vf", "price": 30}, {"grade": "xf", "price": 55}]}
        self.soldcomps_used = 12
        self.scrape_params: list[dict] = []
        self.sold_items = [_sold("1", "40.00", "5.00", "2026-10-20"), _sold("2", "50.00", None, "2026-10-12"),
                           _sold("3", "45.00", "4.50", "2026-10-02"), _sold("4", "60.00", "6.00", "2026-09-28", currency="GBP"),
                           {**_sold("5", None, None, None), "listingType": "active", "currentPrice": "99.00"}]

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
                "updatedAt": self.gold_api_updated.get(symbol, _iso(self.stamp)),
                "updatedAtReadable": "a few seconds ago",
            }
            return httpx.Response(200, json=body)
        if url.host == "api.metals.dev":
            if url.path == "/usage":
                return httpx.Response(
                    200, json={"status": "success", "timestamp": _iso(self.stamp), "plan": "Free", "total": 100, "used": 7, "remaining": 93}
                )
            body = self.metals_dev_body or {
                "status": "success",
                "currency": url.params.get("currency"),
                "unit": "toz",
                "metals": {"gold": 4010.5, "silver": 50.25, "platinum": 1490.0, "palladium": 1105.0, "copper": 0.3},
                "currencies": {},
                "timestamps": {"metal": _iso(self.stamp), "currency": _iso(self.stamp)},
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
            if url.path != "/metal-quote":  # what RapidAPI's gateway says for paths not in the listing
                return httpx.Response(404, json={"message": f"Endpoint '{url.path}' does not exist"})
            sym = url.params.get("symbol")
            body = self.ms_body or {
                "ID": 1793412613,
                "results": [{
                    "symbol": sym, "currency": url.params.get("currency"), "ask": self.ms_prices[sym] + 1,
                    "mid": self.ms_prices[sym], "bid": self.ms_prices[sym] - 1, "high": 0, "low": 0, "open": 0,
                    "close": 0, "timestamp": int(_recent(self.stamp).timestamp()), "change": 0, "changePercentage": 0, "unit": "OUNCE",
                    "originalTime": _iso(self.stamp), "extra": None,
                }],
            }
            return httpx.Response(200, json=body, headers=headers)
        if url.host == "api.numista.com":
            if request.headers.get("Numista-API-Key") != "numista-key":
                return httpx.Response(401, json={"error_message": "Invalid API key"})
            parts = url.path.removeprefix("/v3/").split("/")
            if parts == ["types"]:
                q = url.params.get("q", "").lower()
                hits = [{k: t[k] for k in ("id", "title", "issuer", "min_year", "max_year")} | {"obverse_thumbnail": t["obverse"]["thumbnail"]}
                        for t in self.numista_types.values() if any(w in t["title"].lower() for w in q.split())]
                return httpx.Response(200, json={"count": len(hits), "types": hits})
            tid = int(parts[1])
            if tid not in self.numista_types:
                return httpx.Response(404, json={"error_message": "Type not found"})
            if len(parts) == 2:
                return httpx.Response(200, json=self.numista_types[tid])
            if parts[2:] == ["issues"]:
                return httpx.Response(200, json=self.numista_issues.get(tid, []))
            if parts[2] == "issues" and parts[4:] == ["prices"]:
                return httpx.Response(200, json={"currency": url.params.get("currency", "EUR"), "prices": self.numista_prices.get(int(parts[3]), [])})
            return httpx.Response(404, json={"error_message": "Not found"})
        if url.host == "api.pcgs.com":
            if request.headers.get("Authorization") != "bearer pcgs-token":
                return httpx.Response(500, json={"Message": "An error has occurred."})
            cert = url.path.rsplit("/", 1)[-1]
            coin = self.pcgs_certs.get(cert)
            if coin is None:
                return httpx.Response(200, json={"IsValidRequest": False, "ServerMessage": "No data found"})
            return httpx.Response(200, json={**coin, "CertNo": cert, "IsValidRequest": True, "ServerMessage": "Request successful"})
        if url.host == "api.sold-comps.com" and url.path == "/v1/scrape":
            if request.headers.get("Authorization") != "Bearer sc_testkey1234":
                return httpx.Response(401, json={"error": "Invalid API key"})
            if self.soldcomps_scrape_status == 429:
                return httpx.Response(429, json={"code": "quota_exceeded", "error": "Monthly quota exceeded", "plan": "free",
                                                 "limit": 100, "used": 100, "remaining": 0, "reset_at": "2026-11-14T00:00:00Z"})
            self.soldcomps_used += 1
            self.scrape_params.append(dict(url.params))
            return httpx.Response(200, json={
                "keyword": url.params.get("keyword"), "page": 1, "totalItems": len(self.sold_items),
                "totalResults": "1,200+", "hasNextPage": True, "autoSelectedCategory": None, "items": self.sold_items,
            }, headers={"X-Usage-Limit": "100", "X-Usage-Used": str(self.soldcomps_used),
                        "X-Usage-Remaining": str(100 - self.soldcomps_used), "X-Usage-Reset": "2026-11-14T00:00:00Z"})
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


def _sold(item_id, price, ship, ended, currency="USD"):
    total = None if price is None else str(float(price) + float(ship or 0))
    return {
        "itemId": item_id, "url": f"https://www.ebay.com/itm/{item_id}", "title": f"1881-S Morgan Dollar PCGS MS63 #{item_id}",
        "thumbnailUrl": f"https://i.ebayimg.com/{item_id}.jpg", "condition": "Certified", "conditionId": 3000,
        "buyingFormat": "auction", "bidCount": 7, "listingType": "sold", "endedAt": ended, "soldPrice": price,
        "soldPriceMax": None, "soldCurrency": currency, "bestOfferAccepted": False, "shippingPrice": ship,
        "shippingCurrency": currency, "shippingType": "paid" if ship else "free", "totalPrice": total,
        "scrapedAt": "2026-10-30T12:00:00Z",
    }
