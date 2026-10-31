"""Numista: search, coin details for the form, the cache, and price estimates by grade."""

from decimal import Decimal

import pytest

from app.providers.numista import grade_for, parse_composition
from tests.m2_helpers import FakeProviders


@pytest.fixture
def fake(monkeypatch):
    f = FakeProviders()
    import app.routers.numista as r
    import app.services.provider_admin as pa

    monkeypatch.setattr(r, "http_client", f.client)
    monkeypatch.setattr(pa, "http_client", f.client)
    return f


@pytest.mark.parametrize("text, expect", [
    ("Silver (.925) (.925 silver .075 copper)", ("Ag", Decimal("0.925"))),
    ("Gold (.900)", ("Au", Decimal("0.9"))),
    ("Silver (.999)", ("Ag", Decimal("0.999"))),
    ("Silver (0.835)", ("Ag", Decimal("0.835"))),
    ("Platinum (999.5‰)", ("Pt", Decimal("0.9995"))),
    ("Copper-nickel", None),
    ("Bimetallic: nickel-brass centre in copper-nickel ring", None),
    ("Silver", None),  # no fineness given: nothing to compute with
    (None, None),
])
def test_parse_composition(text, expect):
    assert parse_composition(text) == expect


def test_grade_bands():
    assert grade_for(65, None) == "unc" and grade_for(58, None) == "au" and grade_for(45, None) == "xf"
    assert grade_for(30, None) == "vf" and grade_for(12, None) == "f" and grade_for(8, None) == "vg" and grade_for(4, None) == "g"
    assert grade_for(None, "VF-30") == "vf" and grade_for(None, "EF") == "xf" and grade_for(None, "Unc") == "unc"
    assert grade_for(None, None) is None


def test_needs_a_key(api, fake):
    r = api.get("/api/v1/numista/search", params={"q": "victoria"})
    assert r.status_code == 409 and "Numista API key" in r.json()["detail"]


def test_search_details_and_cache(api, fake):
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    r = api.get("/api/v1/numista/search", params={"q": "victoria cents"})
    assert r.status_code == 200, r.text
    hit = r.json()["types"][0]
    assert hit["id"] == 420 and hit["issuer"] == "Canada" and hit["min_year"] == 1858

    t = api.get("/api/v1/numista/types/420").json()
    assert t["details"] == {"country": "Canada", "denomination": "5 Cents", "numista_id": 420, "diameter_mm": "15.494",
                            "variety_notes": "KM# 2"}
    assert t["metal"] == {"metal": "Ag", "gross_weight_g": "1.167", "fineness": "0.9250"}
    assert [i["id"] for i in t["issues"]] == [9001, 9002, 9003] and t["references"] == ["KM# 2", "Schön# 2"]

    before = len(fake.calls)
    api.get("/api/v1/numista/types/420")
    api.get("/api/v1/numista/search", params={"q": "victoria cents"})
    assert len(fake.calls) == before  # answered from the cache
    usage = next(p for p in api.get("/api/v1/settings/providers").json() if p["key"] == "numista")["usage"]
    assert usage["used"] == 3 and usage["cap"] == 1800

    assert api.get("/api/v1/numista/types/999").status_code == 404


def test_estimate_saves_a_market_value(api, fake):
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    item = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "1858 Canada 5 cents", "details": {"country": "Canada", "year": 1858, "numista_id": 420},
        "condition": {"grading": "raw", "grade_text": "VF-30", "sheldon_grade": 30},
    }).json()
    r = api.post(f"/api/v1/items/{item['id']}/numista/estimate")
    assert r.status_code == 201, r.text
    v = r.json()
    assert Decimal(v["value_each"]) == Decimal("30") and v["currency"] == "USD" and v["source"] == "Numista estimate (VF)"
    assert "F 18.00, VF 30.00, XF 55.00" in v["notes"]
    full = api.get(f"/api/v1/items/{item['id']}").json()
    assert full["details"]["numista_issue_id"] == 9001  # remembered for next time
    assert any("currency=USD" in c or "prices" in c for c in fake.calls)

    # 1870 has two issues (with and without H): the owner has to pick one
    two = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "1870 5 cents", "details": {"year": 1870, "numista_id": 420},
        "condition": {"grading": "raw", "sheldon_grade": 20},
    }).json()
    r = api.post(f"/api/v1/items/{two['id']}/numista/estimate")
    assert r.status_code == 422 and "Pick which issue" in r.json()["detail"]
    # no grade, no estimate
    nograde = api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "details": {"year": 1858, "numista_id": 420}}).json()
    assert api.post(f"/api/v1/items/{nograde['id']}/numista/estimate").status_code == 422
    # a grade Numista doesn't price
    unc = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "unc", "details": {"year": 1858, "numista_id": 420},
        "condition": {"grading": "raw", "sheldon_grade": 63}}).json()
    r = api.post(f"/api/v1/items/{unc['id']}/numista/estimate")
    assert r.status_code == 404 and "has: F, VF, XF" in r.json()["detail"]


def test_test_button_and_bad_key(api, fake):
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    r = api.post("/api/v1/settings/providers/numista/test").json()
    assert r["ok"] and "Key accepted" in r["message"]
    api.put("/api/v1/settings/providers/numista", json={"api_key": "wrong"})
    r = api.post("/api/v1/settings/providers/numista/test").json()
    assert not r["ok"] and "refused the API key" in r["message"]
    r = api.get("/api/v1/numista/search", params={"q": "anything new"})
    assert r.status_code == 409 and "refused" in r.json()["detail"]


def test_estimate_uses_a_grade_written_in_the_title(api, fake):
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    item = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "1858 Canada 5 cents PCGS VF30", "details": {"year": 1858, "numista_id": 420},
    }).json()
    r = api.post(f"/api/v1/items/{item['id']}/numista/estimate")
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "Numista estimate (VF)" and r.json()["notes"].startswith("Grade VF30 taken from the title.")


def test_grade_in_text():
    from app.providers.numista import grade_in_text

    assert grade_in_text("2021 $1 Silver Eagle T1 Last Day Prod PCGS MS70 Legends of Life") == ("MS70", 70)
    assert grade_in_text("1921 Morgan dollar") is None and grade_in_text("VF-30") == ("VF30", 30)


def test_raw_estimate_does_not_override_a_slabbed_coins_value(api, fake):
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    item = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "1858 Canada 5 cents PCGS VF30", "details": {"year": 1858, "numista_id": 420},
        "condition": {"grading": "slabbed", "grading_service": "PCGS", "grade_text": "VF30", "sheldon_grade": 30},
        "valuation_rule": "market",
    }).json()
    api.post(f"/api/v1/items/{item['id']}/valuations", json={"kind": "manual", "value_each": "49.99", "source": "eBay"})
    est = api.post(f"/api/v1/items/{item['id']}/numista/estimate").json()  # newer, but a raw-coin estimate
    vals = api.get(f"/api/v1/items/{item['id']}/valuations").json()
    in_use = [v for v in vals if v["in_use"]]
    assert len(in_use) == 1 and Decimal(in_use[0]["value_each"]) == Decimal("49.99")
    assert Decimal(api.get(f"/api/v1/items/{item['id']}").json()["values"]["current"]) == Decimal("49.99")

    # the owner can choose the estimate anyway, and go back to the automatic choice
    vals = api.put(f"/api/v1/valuations/{est['id']}/use", json={"use": True}).json()
    assert next(v for v in vals if v["in_use"])["id"] == est["id"]
    assert Decimal(api.get(f"/api/v1/items/{item['id']}").json()["values"]["current"]) == Decimal("30")
    vals = api.put(f"/api/v1/valuations/{est['id']}/use", json={"use": False}).json()
    assert Decimal(next(v for v in vals if v["in_use"])["value_each"]) == Decimal("49.99")


def test_raw_coin_uses_the_newest_value(api, fake):
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    item = api.post("/api/v1/items", json={
        "item_type": "coin", "title": "raw", "details": {"year": 1858, "numista_id": 420},
        "condition": {"grading": "raw", "sheldon_grade": 30}, "valuation_rule": "market",
    }).json()
    api.post(f"/api/v1/items/{item['id']}/valuations", json={"kind": "manual", "value_each": "49.99", "as_of": "2026-10-01"})
    api.post(f"/api/v1/items/{item['id']}/numista/estimate")
    assert Decimal(api.get(f"/api/v1/items/{item['id']}").json()["values"]["current"]) == Decimal("30")
