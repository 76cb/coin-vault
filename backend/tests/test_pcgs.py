from decimal import Decimal

import pytest

from app.providers.pcgs import parse_metal
from tests.m2_helpers import FakeProviders


@pytest.fixture
def fake(monkeypatch):
    f = FakeProviders()
    import app.routers.pcgs as r
    import app.services.provider_admin as pa

    monkeypatch.setattr(r, "http_client", f.client)
    monkeypatch.setattr(pa, "http_client", f.client)
    return f


@pytest.mark.parametrize("text, expect", [
    ("90% Silver, 10% Copper", ("Ag", Decimal("0.9"))),
    ("99.9% Silver", ("Ag", Decimal("0.999"))),
    ("91.67% Gold, 3% Silver, 5.33% Copper", ("Au", Decimal("0.9167"))),
    (".999 Fine Silver", ("Ag", Decimal("0.999"))),
    ("Copper-Nickel Clad Copper", None),
    (None, None),
])
def test_parse_metal(text, expect):
    assert parse_metal(text) == expect


def test_lookup_fills_the_form(api, fake):
    assert api.post("/api/v1/pcgs/lookup", json={"cert_no": "32573628"}).status_code == 409  # no token yet
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "pcgs-token"})
    r = api.post("/api/v1/pcgs/lookup", json={"cert_no": "3257-3628"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert Decimal(d["coin"]["price_guide"]) == 45 and d["coin"]["population"] == 1203
    assert d["title"] == "2015-S 25C Bombay Hook NP, Silver PCGS PR70 DCAM"
    assert d["condition"]["cert_number"] == "32573628" and d["condition"]["grade_text"] == "PR70"
    assert d["condition"]["designations"] == ["DCAM"] and d["condition"]["sheldon_grade"] == 70
    assert d["metal"] == {"metal": "Ag", "gross_weight_g": "6.25", "fineness": "0.9000"}
    assert d["details"]["pcgs_number"] == "539704" and d["details"]["mint_mark"] == "S"
    prov = next(p for p in api.get("/api/v1/settings/providers").json() if p["key"] == "pcgs")
    assert prov["usage"]["used"] == 1 and prov["quota_period"] == "calendar_day"

    missing = api.post("/api/v1/pcgs/lookup", json={"cert_no": "11111111"})
    assert missing.status_code == 404 and "No data found" in missing.json()["detail"]
    assert api.post("/api/v1/pcgs/lookup", json={"cert_no": "12ab"}).status_code == 422


def test_bad_token_and_test_button(api, fake):
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "wrong"})
    r = api.post("/api/v1/pcgs/lookup", json={"cert_no": "32573628"})
    assert r.status_code == 409 and "refused the token" in r.json()["detail"]
    assert not api.post("/api/v1/settings/providers/pcgs/test").json()["ok"]
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "pcgs-token"})
    ok = api.post("/api/v1/settings/providers/pcgs/test").json()
    assert ok["ok"] and ok["message"].startswith("Token accepted")


def test_daily_cap(api, fake):
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "pcgs-token", "quota_cap": 1})
    assert api.post("/api/v1/pcgs/lookup", json={"cert_no": "32573628"}).status_code == 200
    r = api.post("/api/v1/pcgs/lookup", json={"cert_no": "32573628"})
    assert r.status_code == 429 and "used up" in r.json()["detail"]


def test_price_guide_becomes_market_value(api, fake):
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "pcgs-token"})
    item = api.post("/api/v1/items", json={"item_type": "coin", "title": "Bombay Hook", "condition": {
        "grading": "slabbed", "grading_service": "PCGS", "cert_number": "32573628", "grade_text": "PR70"}}).json()
    r = api.post(f"/api/v1/items/{item['id']}/pcgs/price-guide")
    assert r.status_code == 201, r.text
    v = r.json()
    assert Decimal(v["value_each"]) == 45 and v["source"] == "PCGS Price Guide (PR70)"
    assert "Population 1203" in v["notes"]
    got = api.get(f"/api/v1/items/{item['id']}").json()
    assert Decimal(got["values"]["market"]) == 45 and got["details"]["pcgs_number"] == "539704"
    raw = api.post("/api/v1/items", json={"item_type": "coin", "title": "Raw"}).json()
    assert api.post(f"/api/v1/items/{raw['id']}/pcgs/price-guide").status_code == 422
