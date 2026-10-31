import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.m2_helpers import FakeProviders


@pytest.fixture
def fake(monkeypatch):
    f = FakeProviders()
    import app.services.provider_admin as pa
    import app.services.spot as spot

    monkeypatch.setattr(spot, "http_client", f.client)
    monkeypatch.setattr(pa, "http_client", f.client)
    return f


def add_spot(metal, price, currency="USD", minutes_ago=1):
    from app.db import session_factory
    from app.models import SpotPrice, utcnow

    with session_factory()() as db:
        db.add(SpotPrice(metal=metal, currency=currency, price_per_toz=Decimal(price), source="gold_api",
                         fetched_at=utcnow() - dt.timedelta(minutes=minutes_ago)))
        db.commit()


def test_compositions_seeded_and_matched(api):
    rows = api.get("/api/v1/compositions").json()
    keys = {r["key"] for r in rows}
    assert {"us-dime-90", "us-war-nickel-35", "ase-1oz", "krugerrand-1oz", "us-90-per-face"} <= keys
    m = lambda **q: [r["key"] for r in api.get("/api/v1/compositions/match", params=q).json()]  # noqa: E731
    assert m(country="United States", denomination="Quarter", year=1964)[0] == "us-quarter-90"
    assert m(country="United States", denomination="50c", year=1967)[0] == "us-half-40"
    assert m(country="United States", denomination="Half Dollar", year=1964)[0] == "us-half-90"
    assert m(country="United States", denomination="$1", year=1921, series="Peace Dollar")[0] == "us-dollar-90"
    assert m(country="United States", denomination="5c", year=1943, mint_mark="P")[0] == "us-war-nickel-35"
    assert m(country="United States", denomination="5c", year=1950) == []
    # An 1881 dollar could be silver or gold: both come back with the same score.
    both = api.get("/api/v1/compositions/match", params={"country": "United States", "denomination": "Dollar", "year": 1881}).json()
    assert {r["key"] for r in both[:2]} == {"us-dollar-90", "us-gold-1"} and both[0]["score"] == both[1]["score"]
    # A word from the title settles it; "Dollar" alone doesn't.
    assert m(country="United States", denomination="Dollar", year=1881, series="1881-S Morgan Dollar")[0] == "us-dollar-90"
    tie = api.get("/api/v1/compositions/match", params={"country": "United States", "denomination": "Dollar", "year": 1881, "series": "Some Dollar"}).json()
    assert tie[0]["score"] == tie[1]["score"]
    assert "us-90-per-face" in [r["key"] for r in api.get("/api/v1/compositions?per_face=true").json()]


def test_per_face_composition_rejected_on_coin(api):
    per_face = next(r for r in api.get("/api/v1/compositions?per_face=true").json())
    r = api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "metal_content": [{"metal": "Ag", "composition_id": per_face["id"]}]})
    assert r.status_code == 422


def test_custom_composition(api):
    r = api.post("/api/v1/compositions", json={"label": "Swiss 5 francs 1931-1969", "metal": "Ag", "gross_weight_g": "15", "fineness": "0.835"})
    assert r.status_code == 201 and Decimal(r.json()["pure_toz"]) == Decimal("0.402688") and r.json()["custom"]
    assert api.delete(f"/api/v1/compositions/{r.json()['id']}").status_code == 204
    seeded = api.get("/api/v1/compositions?q=Krugerrand").json()[0]
    assert api.delete(f"/api/v1/compositions/{seeded['id']}").status_code == 404


def test_item_values_and_dashboard(api):
    add_spot("Ag", "30")
    add_spot("Au", "4000")
    comp = api.get("/api/v1/compositions?q=Morgan").json()[0]["id"]
    api.post("/api/v1/items", json={"item_type": "coin", "title": "Morgan", "quantity": 2, "purchase_price": "60",
                                    "metal_content": [{"metal": "Ag", "composition_id": comp}]})
    api.post("/api/v1/items", json={"item_type": "bullion", "title": "Gold tenth", "metal_content": [{"metal": "Au", "pure_toz": "0.1"}]})
    sold = api.post("/api/v1/items", json={"item_type": "coin", "title": "Sold", "metal_content": [{"metal": "Ag", "pure_toz": "10"}]}).json()
    api.post(f"/api/v1/items/{sold['id']}/sell", json={"sale_date": "2026-10-01", "sale_price": "300"})

    morgan = api.get("/api/v1/items?q=Morgan").json()["items"][0]
    assert Decimal(morgan["melt"]) == Decimal("46.41")  # 2 x 0.773451 x 30
    full = api.get(f"/api/v1/items/{morgan['id']}").json()
    assert full["values"]["rule_applied"] == "melt" and Decimal(full["values"]["gain"]) == Decimal("-13.59")

    s = api.get("/api/v1/portfolio/summary").json()
    t = s["totals"]
    assert t["item_count"] == 2  # sold items are not holdings
    assert Decimal(t["melt"]) == Decimal("446.41") and Decimal(t["cost"]) == Decimal("60.00")
    assert t["cost_unknown_items"] == 1 and t["gain_items"] == 1
    assert {b["key"] for b in s["by_metal"]} == {"Ag", "Au"}
    assert s["spot"]["currency"] == "USD" and any(m["metal"] == "Ag" and Decimal(m["price"]) == 30 for m in s["spot"]["metals"])
    assert s["by_location"][0]["label"] == "No location"

    h = api.get("/api/v1/prices/spot/history?metal=Ag&days=1").json()
    assert Decimal(h["holdings_toz"]) == Decimal("1.546902") and len(h["points"]) == 1


def test_refresh_uses_providers(api, fake):
    r = api.post("/api/v1/prices/spot/refresh")
    assert r.status_code == 200 and r.json()["source"] == "gold_api"
    latest = api.get("/api/v1/prices/spot/latest").json()
    assert {m["metal"]: Decimal(m["price"]) for m in latest["metals"]}["Au"] == Decimal("4000")
    calls = api.get("/api/v1/settings/providers/gold_api/calls").json()
    assert calls[0]["status"] == "ok"


def test_provider_key_is_encrypted_and_never_returned(api):
    from app.db import session_factory
    from app.models import ProviderConfig

    r = api.put("/api/v1/settings/providers/soldcomps", json={"api_key": "sc_testkey1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["key_set"] and body["key_last4"] == "1234" and "sc_testkey1234" not in r.text
    with session_factory()() as db:
        stored = db.scalar(select(ProviderConfig.api_key_encrypted).where(ProviderConfig.provider_key == "soldcomps"))
    assert stored.startswith("v1:") and "sc_testkey1234" not in stored
    listed = api.get("/api/v1/settings/providers").text
    assert "sc_testkey1234" not in listed
    assert api.put("/api/v1/settings/providers/soldcomps", json={"api_key": None}).json()["key_set"] is False
    assert api.put("/api/v1/settings/providers/gold_api", json={"api_key": "x"}).status_code == 422
    assert api.put("/api/v1/settings/providers/nope", json={"enabled": True}).status_code == 404


def test_soldcomps_test_button_syncs_usage(api, fake):
    api.put("/api/v1/settings/providers/soldcomps", json={"api_key": "sc_testkey1234", "quota_cap": 90})
    r = api.post("/api/v1/settings/providers/soldcomps/test").json()
    assert r["ok"] and "12 of 100" in r["message"]
    usage = r["provider"]["usage"]
    assert usage["used"] == 12 and usage["provider_limit"] == 100 and usage["remaining"] == 78
    assert usage["period_start"].startswith("2026-10-14") and usage["period_end"].startswith("2026-11-14")
    assert fake.calls == ["api.sold-comps.com/usage"]  # free endpoint only; no search spent
    hist = api.get("/api/v1/settings/providers/soldcomps/usage").json()
    assert hist["days"][0]["calls"] == 1 and hist["days"][0]["requests"] == 0

    api.put("/api/v1/settings/providers/soldcomps", json={"api_key": "sc_wrongkey"})
    bad = api.post("/api/v1/settings/providers/soldcomps/test").json()
    assert not bad["ok"] and "401" in bad["message"]


def test_metals_dev_and_gold_api_test(api, fake):
    api.put("/api/v1/settings/providers/metals_dev", json={"api_key": "md-key"})
    r = api.post("/api/v1/settings/providers/metals_dev/test").json()
    assert r["ok"] and r["provider"]["usage"]["used"] == 7
    g = api.post("/api/v1/settings/providers/gold_api/test").json()
    assert g["ok"] and "Gold 4,000 USD" in g["message"]
    assert api.post("/api/v1/settings/providers/soldcomps/test").json()["message"] == "No API key saved yet."


def test_settings_need_session_not_token(api, client):
    token = api.post("/api/v1/auth/tokens", json={"name": "t", "scopes": ["items:read", "prices:read"]}).json()["token"]
    fresh = client.__class__(client.app)
    h = {"Authorization": f"Bearer {token}"}
    assert fresh.get("/api/v1/settings/providers", headers=h).status_code == 403
    assert fresh.get("/api/v1/portfolio/summary", headers=h).status_code == 200


def test_app_settings(api):
    s = api.get("/api/v1/settings").json()
    assert s["base_currency"] == "USD" and s["spot_poll_minutes"] == 15 and s["encryption_ready"]
    assert api.patch("/api/v1/settings", json={"base_currency": "XYZ"}).status_code == 422
    s = api.patch("/api/v1/settings", json={"base_currency": "eur", "spot_stale_minutes": 45}).json()
    assert s["base_currency"] == "EUR" and s["spot_stale_minutes"] == 45
    assert api.patch("/api/v1/settings", json={"spot_poll_minutes": 1}).status_code == 422


def test_missing_encryption_key(api, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "encryption_key", None)
    r = api.put("/api/v1/settings/providers/metals_dev", json={"api_key": "abc"})
    assert r.status_code == 503 and "CV_ENCRYPTION_KEY" in r.json()["detail"]


def test_metal_sentinel_test_button(api, fake):
    api.put("/api/v1/settings/providers/metal_sentinel", json={"api_key": "rapid-key"})
    r = api.post("/api/v1/settings/providers/metal_sentinel/test").json()
    assert r["ok"] and "market is open" in r["message"] and "101 of 7500" in r["message"]
    assert r["provider"]["usage"]["used"] == 101 and r["provider"]["usage"]["provider_limit"] == 7500
    assert fake.calls == ["metal-sentinel.p.rapidapi.com/api/market-status"]
    calls = api.get("/api/v1/settings/providers/metal_sentinel/calls").json()
    assert calls[0]["cost"] == 1  # RapidAPI counts every request, so the Test button does too
    fake.ms_status = 403
    bad = api.post("/api/v1/settings/providers/metal_sentinel/test").json()
    assert not bad["ok"] and "refused the key" in bad["message"]
