from decimal import Decimal

import pytest

from tests.m2_helpers import FakeProviders


@pytest.fixture
def fake(monkeypatch):
    f = FakeProviders()
    import app.routers.valuations as v

    monkeypatch.setattr(v, "http_client", f.client)
    return f


def _item(api, **extra):
    body = {"item_type": "coin", "title": "1881-S Morgan Dollar", "quantity": 2, "purchase_price": "60",
            "metal_content": [{"metal": "Ag", "pure_toz": "0.773451"}], **extra}
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _spot(price="30"):
    from app.db import session_factory
    from app.models import SpotPrice, utcnow

    with session_factory()() as db:
        db.add(SpotPrice(metal="Ag", currency="USD", price_per_toz=Decimal(price), source="gold_api", fetched_at=utcnow()))
        db.commit()


def test_manual_value_drives_current_value(api):
    _spot()
    it = _item(api)
    assert it["values"]["rule_applied"] == "melt" and it["values"]["market"] is None
    r = api.post(f"/api/v1/items/{it['id']}/valuations",
                 json={"value_each": "85", "as_of": "2026-10-20", "source": "Dealer quote", "notes": "Coin show"})
    assert r.status_code == 201 and r.json()["kind"] == "manual" and r.json()["currency"] == "USD"
    v = api.get(f"/api/v1/items/{it['id']}").json()["values"]
    assert Decimal(v["market"]) == Decimal("170.00") and Decimal(v["market_each"]) == Decimal("85")
    assert v["rule_applied"] == "market" and Decimal(v["current"]) == Decimal("170.00")  # higher than melt 46.41
    assert v["market_source"] == "Dealer quote" and v["market_as_of"] == "2026-10-20"
    # the newest by date wins, not the newest entered
    api.post(f"/api/v1/items/{it['id']}/valuations", json={"value_each": "70", "as_of": "2026-09-01"})
    assert Decimal(api.get(f"/api/v1/items/{it['id']}").json()["values"]["market_each"]) == Decimal("85")
    hist = api.get(f"/api/v1/items/{it['id']}/valuations").json()
    assert [h["as_of"] for h in hist] == ["2026-10-20", "2026-09-01"]
    s = api.get("/api/v1/portfolio/summary").json()
    assert Decimal(s["totals"]["market"]) == Decimal("170.00") and s["totals"]["valued_at_market"] == 1
    assert s["market_values_available"] is True
    assert api.delete(f"/api/v1/valuations/{hist[0]['id']}").status_code == 204
    assert Decimal(api.get(f"/api/v1/items/{it['id']}").json()["values"]["market_each"]) == Decimal("70")
    assert api.post(f"/api/v1/items/{it['id']}/valuations", json={"value_each": "0"}).status_code == 422
    assert api.post(f"/api/v1/items/{it['id']}/valuations", json={}).status_code == 422


def test_comps_search_and_save_median(api, fake):
    it = _item(api, condition={"grading": "slabbed", "grading_service": "PCGS", "grade_text": "MS63"})
    kw = api.get(f"/api/v1/items/{it['id']}/comps/keyword").json()["keyword"]
    assert kw == "1881-S Morgan Dollar PCGS MS63"
    assert api.post(f"/api/v1/items/{it['id']}/comps/search", json={"keyword": kw}).status_code == 409  # no key yet

    api.put("/api/v1/settings/providers/soldcomps", json={"api_key": "sc_testkey1234"})
    r = api.post(f"/api/v1/items/{it['id']}/comps/search", json={"keyword": kw, "sold_within_days": 60})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [l["item_id"] for l in out["listings"]] == ["1", "2", "3"]  # active and GBP listings left out
    assert out["other_currency"] == 1 and out["total_results"] == "1,200+"
    assert out["stats"] == {"count": 3, "low": "40.00", "median": "45.00", "high": "50.00"}
    assert out["requests_used"] == 13 and out["requests_limit"] == 100
    p = fake.scrape_params[0]
    assert p["sold"] == "true" and p["keyword"] == kw and p["soldAfter"] and p["exactMatch"] == "true"
    prov = next(x for x in api.get("/api/v1/settings/providers").json() if x["key"] == "soldcomps")
    assert prov["usage"]["used"] == 13  # SoldComps' own count from the headers

    picked = out["listings"][:2]  # 40 + 5 ship, 50 free ship
    r = api.post(f"/api/v1/items/{it['id']}/valuations",
                 json={"kind": "comps", "comps": {"keyword": kw, "basis": "total", "listings": picked}})
    assert r.status_code == 201
    v = r.json()
    assert Decimal(v["value_each"]) == Decimal("47.50") and v["details"]["count"] == 2
    assert v["source"] == "Median of 2 eBay sold listings (SoldComps)"
    assert v["details"]["listings"][0]["url"] == "https://www.ebay.com/itm/1"


def test_comps_errors(api, fake):
    it = _item(api)
    api.put("/api/v1/settings/providers/soldcomps", json={"api_key": "sc_wrong"})
    r = api.post(f"/api/v1/items/{it['id']}/comps/search", json={"keyword": "Morgan"})
    assert r.status_code == 409 and "rejected the API key" in r.json()["detail"]
    api.put("/api/v1/settings/providers/soldcomps", json={"api_key": "sc_testkey1234"})
    fake.soldcomps_scrape_status = 429
    r = api.post(f"/api/v1/items/{it['id']}/comps/search", json={"keyword": "Morgan"})
    assert r.status_code == 429 and "quota used up" in r.json()["detail"]
    api.put("/api/v1/settings/providers/soldcomps", json={"quota_cap": 0})
    fake.soldcomps_scrape_status = 200
    r = api.post(f"/api/v1/items/{it['id']}/comps/search", json={"keyword": "Morgan"})
    assert r.status_code == 429 and "cap" in r.json()["detail"]
    assert fake.scrape_params == []  # the cap stopped it before any call


def test_valuations_are_private(api, client):
    it = _item(api)
    v = api.post(f"/api/v1/items/{it['id']}/valuations", json={"value_each": "85"}).json()
    from tests.conftest import _make_user

    _make_user("other", admin=False)
    other = client.__class__(client.app)
    me = other.post("/api/v1/auth/login", json={"username": "other", "password": "correct horse battery"}).json()
    h = {"X-CSRF-Token": me["csrf_token"]}
    assert other.get(f"/api/v1/items/{it['id']}/valuations").status_code == 404
    assert other.delete(f"/api/v1/valuations/{v['id']}", headers=h).status_code == 404
