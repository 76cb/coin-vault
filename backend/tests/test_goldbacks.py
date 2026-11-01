"""Goldbacks: their own type, gold worked out from the denomination, added several at once, and counted."""

from decimal import Decimal

from app.services.describe import describe


def test_catalogue(api):
    c = api.get("/api/v1/goldbacks/catalogue").json()
    assert {"name": "Utah", "first_year": 2019} in c["series"]
    by = {d["label"]: d for d in c["denominations"]}
    assert Decimal(by["1/2"]["gold_toz"]) == Decimal("0.0005") and Decimal(by["100"]["gold_toz"]) == Decimal("0.1")
    assert by["5"]["common"] and not by["3"]["common"]


def test_a_goldback_gets_its_gold_from_its_denomination(api):
    r = api.post("/api/v1/items", json={"item_type": "goldback", "title": "Utah Goldback 5", "quantity": 4,
                                         "details": {"state": "Utah", "denomination": "5", "year": 2019}})
    assert r.status_code == 201, r.text
    it = r.json()
    assert [(m["metal"], Decimal(m["pure_toz"])) for m in it["metal_content"]] == [("Au", Decimal("0.005"))]
    m = it["metal_content"][0]
    assert Decimal(m["fineness"]) == Decimal("0.9999") and Decimal(m["gross_weight_g"]) == Decimal("0.155517")  # 0.005 oz in grams
    assert it["values"] is None or it["values"]["pure_toz_total"]["Au"] in ("0.020000", "0.02")
    # changing the denomination changes the gold
    r = api.patch(f"/api/v1/items/{it['id']}", json={"details": {"denomination": "25"}}, headers={"If-Match": str(it["version"])})
    assert Decimal(r.json()["metal_content"][0]["pure_toz"]) == Decimal("0.025")
    assert api.post("/api/v1/items", json={"item_type": "goldback", "title": "x", "details": {"denomination": "7"}}).status_code == 422


def test_add_several_and_count_them(api):
    r = api.post("/api/v1/goldbacks", json={
        "state": "Nevada", "year": 2020, "acquired_date": "2026-10-01",
        "rows": [{"denomination": "1", "quantity": 10, "price_total": "55"}, {"denomination": "0.5", "quantity": 4}],
    })
    assert r.status_code == 201, r.text
    ids = r.json()["item_ids"]
    first = api.get(f"/api/v1/items/{ids[0]}").json()
    assert first["title"] == "2020 Nevada Goldback 1" and first["quantity"] == 10 and Decimal(first["purchase_price"]) == 55
    assert api.get(f"/api/v1/items/{ids[1]}").json()["title"] == "2020 Nevada Goldback 1/2"
    api.post("/api/v1/goldbacks", json={"state": "Utah", "rows": [{"denomination": "5", "quantity": 2}]})
    assert api.post("/api/v1/goldbacks", json={"state": "Utah", "rows": [{"denomination": "5", "quantity": 1}, {"denomination": "5", "quantity": 1}]}).status_code == 422

    s = api.get("/api/v1/goldbacks/summary").json()
    rows = {(r["state"], r["label"]): r for r in s["rows"]}
    assert rows[("Nevada", "1")]["notes"] == 10 and Decimal(rows[("Nevada", "1")]["gold_toz"]) == Decimal("0.01")
    assert rows[("Nevada", "1/2")]["notes"] == 4 and Decimal(rows[("Nevada", "1/2")]["goldbacks"]) == 2
    assert rows[("Utah", "5")]["notes"] == 2
    assert s["notes"] == 16 and Decimal(s["goldbacks"]) == Decimal(22) and Decimal(s["gold_toz"]) == Decimal("0.022")
    # filtering the collection by type finds them
    listed = api.get("/api/v1/items", params={"type": "goldback", "per_page": "50"}).json()
    assert {i["id"] for i in listed["items"]} >= set(ids)


def test_title_reader():
    d = describe("10 x 1/2 Goldback Nevada 2021")
    assert d.item_type == "goldback" and d.quantity == 10
    assert d.details == {"state": "Nevada", "denomination": "0.5", "year": 2021} and d.title == "2021 Nevada Goldback 1/2"
    assert describe("Goldback Dallas Fort Worth 50").details["denomination"] == "50"
    assert describe("Utah Goldback 5").details == {"state": "Utah", "denomination": "5"}


def test_describe_endpoint(api):
    d = api.post("/api/v1/items/describe", json={"text": "Wyoming Goldback 25"}).json()
    assert d["item_type"] == "goldback" and d["details"]["state"] == "Wyoming" and d["compositions"] == []
