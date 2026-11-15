"""Collection tools, money figures, alerts, the want list, checklists, sales, labels, read-only logins and CSV import."""

import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient

from app.services import checklists as cl
from tests.conftest import PASSWORD, Api


def _create(api, body: dict) -> dict:
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _spot(**prices: str) -> None:
    from app.db import session_factory
    from app.models import SpotPrice

    with session_factory()() as db:
        for metal, price in prices.items():
            db.add(SpotPrice(metal=metal, currency="USD", price_per_toz=Decimal(price), source="test"))
        db.commit()


def _ids(api, **params) -> list[int]:
    r = api.get("/api/v1/items", params=params)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]]


EAGLE = {"item_type": "bullion", "title": "2023 American Silver Eagle", "details": {"year": 2023, "product_line": "American Silver Eagle"},
         "metal_content": [{"metal": "Ag", "gross_weight_g": "31.103", "fineness": "0.999", "pure_toz": "1"}]}


def test_needs_attention_and_value_sorts(api):
    _spot(Ag="30", Au="2000")
    eagle = _create(api, {**EAGLE, "purchase_price": "40"})                       # melt 30, cost 40
    gold = _create(api, {"item_type": "bar", "title": "1 oz gold bar", "details": {"weight_value": "1", "weight_unit": "ozt"},
                         "metal_content": [{"metal": "Au", "fineness": "0.9999"}], "purchase_price": "1500"})  # melt ~2000
    bare = _create(api, {"item_type": "bar", "title": "Mystery bar"})             # no metal, cost or value
    cent = _create(api, {"item_type": "coin", "title": "2001 cent", "details": {"country": "United States", "denomination": "1c", "year": 2001}})
    note = _create(api, {"item_type": "banknote", "title": "Old note", "purchase_price": "5"})

    by = {i["id"]: i for i in api.get("/api/v1/items").json()["items"]}
    assert by[eagle["id"]]["gaps"] == ["photos"] and by[bare["id"]]["gaps"] == ["metal", "cost", "photos", "value"]
    assert "metal" not in by[cent["id"]]["gaps"]  # a zinc cent has its composition: nothing to add
    assert "metal" not in by[note["id"]]["gaps"]
    assert set(_ids(api, missing="metal")) == {bare["id"]}
    assert set(_ids(api, missing="cost")) == {bare["id"], cent["id"]}
    assert len(_ids(api, missing="any")) == 5 and set(_ids(api, missing="value")) == {bare["id"], cent["id"], note["id"]}
    assert _ids(api, sort="value")[:3] == [gold["id"], eagle["id"], note["id"]]  # largest first, no value last
    assert _ids(api, sort="gain")[:2] == [gold["id"], eagle["id"]] and _ids(api, sort="cost")[0] == gold["id"]
    assert _ids(api, sort="melt", page_size=1, page=2) == [eagle["id"]]
    page = api.get("/api/v1/items", params={"missing": "any", "page_size": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    csv = api.get("/api/v1/export/items.csv", params={"missing": "metal", "sort": "value"}).text
    assert "Mystery bar" in csv and "Silver Eagle" not in csv

    one = api.get(f"/api/v1/items/{eagle['id']}").json()
    assert Decimal(one["values"]["premium"]) == Decimal("10.00") and one["gaps"] == ["photos"]
    s = api.get("/api/v1/portfolio/summary").json()
    assert s["totals"]["premium_items"] == 2 and Decimal(s["totals"]["premium_cost"]) == Decimal("1540")
    silver = next(b for b in s["by_metal"] if b["key"] == "Ag")
    assert Decimal(silver["cost_per_toz"]) == Decimal("40.00")
    assert Decimal(next(b for b in s["by_metal"] if b["key"] == "Au")["cost_per_toz"]) == Decimal("1500.15")  # 1500 / 0.9999


def test_bulk_edit_and_inventory_check(api):
    a, b, c = (_create(api, {**EAGLE, "title": f"Eagle {n}", "tags": ["old"]}) for n in "abc")
    box = api.post("/api/v1/locations", json={"name": "Box A"}).json()
    r = api.post("/api/v1/items/bulk", json={"ids": [a["id"], b["id"]], "location_id": box["id"], "add_tags": ["Stack"], "remove_tags": ["old"],
                                              "status": "for_sale", "verified": True})
    assert r.status_code == 200 and r.json() == {"changed": 2}
    got = api.get(f"/api/v1/items/{a['id']}").json()
    assert got["location_path"] == "Box A" and got["tags"] == ["Stack"] and got["status"] == "for_sale"
    assert got["verified_at"] and got["version"] == 2
    assert any(e["field"] == "status" for e in api.get(f"/api/v1/items/{a['id']}/audit").json())
    assert api.get(f"/api/v1/items/{c['id']}").json()["tags"] == ["old"]
    # tags only: the location is left alone; null moves to "no location"
    api.post("/api/v1/items/bulk", json={"ids": [a["id"]], "add_tags": ["x"]})
    assert api.get(f"/api/v1/items/{a['id']}").json()["location_path"] == "Box A"
    api.post("/api/v1/items/bulk", json={"ids": [a["id"]], "location_id": None})
    assert api.get(f"/api/v1/items/{a['id']}").json()["location_path"] is None
    assert api.post("/api/v1/items/bulk", json={"ids": [a["id"], 99999], "verified": True}).status_code == 404
    assert api.post("/api/v1/items/bulk", json={"ids": [a["id"]], "location_id": 99999}).status_code == 422
    # one item at a time
    assert api.post(f"/api/v1/items/{c['id']}/verify").json()["verified_at"]
    assert api.post(f"/api/v1/items/{c['id']}/verify", params={"seen": False}).json()["verified_at"] is None
    assert api.post("/api/v1/items/bulk", json={"ids": [b["id"], c["id"]], "delete": True}).json() == {"changed": 2}
    assert _ids(api) == [a["id"]] and set(_ids(api, deleted=True)) == {b["id"], c["id"]}


def test_spot_alerts(api):
    _spot(Ag="30")
    low = api.post("/api/v1/alerts", json={"metal": "Ag", "direction": "below", "price": "25", "note": "buy"}).json()
    assert low["triggered_at"] is None and Decimal(low["spot"]) == Decimal("30")
    high = api.post("/api/v1/alerts", json={"metal": "Ag", "direction": "above", "price": "28"}).json()
    by = {a["id"]: a for a in api.get("/api/v1/alerts").json()}
    assert by[high["id"]]["triggered_at"] and Decimal(by[high["id"]]["triggered_price"]) == Decimal("30")  # already past it
    assert by[low["id"]]["triggered_at"] is None

    from app.db import session_factory
    from app.services import alerts

    with session_factory()() as db:
        assert alerts.check(db, "USD", {"Ag": Decimal("26")}) == []
        fired = alerts.check(db, "USD", {"Ag": Decimal("24.5")})
        assert [a.id for a in fired] == [low["id"]] and alerts.check(db, "USD", {"Ag": Decimal("20")}) == []  # fires once
    assert api.post(f"/api/v1/alerts/{low['id']}/dismiss").json()["dismissed_at"]
    again = api.post(f"/api/v1/alerts/{low['id']}/rearm").json()
    assert again["triggered_at"] is None and again["dismissed_at"] is None
    assert api.delete(f"/api/v1/alerts/{low['id']}").status_code == 204 and len(api.get("/api/v1/alerts").json()) == 1
    assert api.post("/api/v1/alerts", json={"metal": "Ag", "direction": "sideways", "price": "1"}).status_code == 422


def test_want_list(api):
    w = api.post("/api/v1/wants", json={"title": "1893-S Morgan Dollar", "target_price": "4500", "notes": "VF or better"}).json()
    api.post("/api/v1/wants", json={"title": "1916-D Mercury Dime"})
    item = _create(api, {"item_type": "coin", "title": "1893-S Morgan Dollar"})
    got = api.patch(f"/api/v1/wants/{w['id']}", json={"found_item_id": item["id"]}).json()
    assert got["found_at"] and got["found_item_id"] == item["id"]
    assert [x["title"] for x in api.get("/api/v1/wants").json()] == ["1916-D Mercury Dime", "1893-S Morgan Dollar"]  # found ones last
    back = api.patch(f"/api/v1/wants/{w['id']}", json={"found": False, "target_price": "4000"}).json()
    assert back["found_at"] is None and back["found_item_id"] is None and Decimal(back["target_price"]) == Decimal("4000")
    assert api.delete(f"/api/v1/wants/{w['id']}").status_code == 204 and len(api.get("/api/v1/wants").json()) == 1


def test_checklist_definitions():
    by = {c.key: c for c in cl.all_checklists(2026)}
    counts = {k: len(c.entries) for k, c in by.items()}
    assert counts == {"state-quarters": 50, "territory-quarters": 6, "atb-quarters": 56, "women-quarters": 20, "presidential-dollars": 39,
                      "morgan-dollars": 96, "peace-dollars": 24, "franklin-halves": 35, "silver-eagles": 41}
    labels = [e.label for e in by["morgan-dollars"].entries]
    assert "1893-S Morgan dollar" in labels and "1889-CC Morgan dollar" in labels and "1921 Morgan dollar" in labels
    assert "1886-CC Morgan dollar" not in labels and len(set(labels)) == 96


def test_checklists_count_coins_and_coins_in_sets(api):
    d = api.post("/api/v1/items/describe", json={"text": "2008 United States 50 State Quarters Silver Proof Set"}).json()
    proof = _create(api, {"item_type": "set", "title": d["title"], "details": d["details"]})
    loose = _create(api, {"item_type": "coin", "title": "1999 Delaware State Quarter", "details": {"country": "United States", "denomination": "25c", "year": 1999, "series": "50 State Quarters"}})
    _create(api, {"item_type": "coin", "title": "2005-S West Virginia quarter", "details": {"denomination": "25c", "year": 2005, "mint_mark": "S"}})
    morgan = _create(api, {"item_type": "coin", "title": "1881-S Morgan Dollar", "details": {"denomination": "$1", "year": 1881, "mint_mark": "S", "series": "Morgan"}})
    _create(api, {"item_type": "coin", "title": "1921 Morgan Dollar", "details": {"denomination": "$1", "year": 1921, "mint_mark": "P", "series": "Morgan"}})
    _create(api, {"item_type": "coin", "title": "1921 Peace Dollar", "details": {"denomination": "$1", "year": 1921}})
    _create(api, EAGLE)
    sold = _create(api, {"item_type": "coin", "title": "1880-S Morgan Dollar", "status": "sold", "sale_date": "2026-01-02", "sale_price": "50",
                         "details": {"denomination": "$1", "year": 1880, "mint_mark": "S"}})
    have = {c["key"]: c["have"] for c in api.get("/api/v1/checklists").json()}
    assert have == {"state-quarters": 7, "territory-quarters": 0, "atb-quarters": 0, "women-quarters": 0, "presidential-dollars": 0,
                    "morgan-dollars": 2, "peace-dollars": 1, "franklin-halves": 0, "silver-eagles": 1}
    q = api.get("/api/v1/checklists/state-quarters").json()
    by = {e["label"]: e for e in q["entries"]}
    assert by["2008 Oklahoma quarter"]["have"] == [{"id": proof["id"], "title": d["title"], "in_set": True}]
    assert by["1999 Delaware quarter"]["have"][0]["id"] == loose["id"] and by["1999 Delaware quarter"]["group"] == "1999"
    assert by["2005 West Virginia quarter"]["have"] and by["2000 Virginia quarter"]["have"] == []
    m = {e["label"]: e["have"] for e in api.get("/api/v1/checklists/morgan-dollars").json()["entries"]}
    assert m["1881-S Morgan dollar"][0]["id"] == morgan["id"] and m["1881 Morgan dollar"] == [] and m["1921 Morgan dollar"]  # P is "no mint mark"
    assert m["1880-S Morgan dollar"] == [] and sold["status"] == "sold"  # sold coins don't count
    assert api.get("/api/v1/checklists/nope").status_code == 404


def test_uncirculated_sets_fill_in(api):
    d = api.post("/api/v1/items/describe", json={"text": "2008 US Mint Uncirculated Coin Set"}).json()
    coins = [c["label"] for c in d["details"]["coins"]]
    assert len(coins) == 28 and coins[0] == "2008 Lincoln cent" and "2008-D Oklahoma quarter" in coins and "2008-P Kennedy half dollar" in coins
    assert all(c.get("metal") is None for c in d["details"]["coins"]) and "28 coins, no silver" in d["recognized"]
    assert api.get("/api/v1/reference/mint-set", params={"year": 1998, "kind": "uncirculated"}).json() is None


def test_sales_report(api):
    def sold(title, bought, paid, when, price, fees=None, status="known"):
        return _create(api, {"item_type": "coin", "title": title, "acquired_date": bought, "purchase_price": paid, "cost_basis_status": status if paid else None,
                             "status": "sold", "sale_date": when, "sale_price": price, "sale_fees": fees, "sale_venue": "eBay"})

    sold("Long hold", "2024-01-10", "100", "2026-03-01", "180", "12")       # +68, long
    sold("Quick flip", "2026-01-05", "50", "2026-02-01", "45")              # -5, short
    sold("No date", None, "20", "2026-04-01", "30")                         # +10, holding period unknown
    sold("No cost", None, None, "2026-05-01", "75")
    sold("Last year", "2020-01-01", "10", "2025-06-01", "40")               # +30
    _create(api, EAGLE)
    r = api.get("/api/v1/reports/sales").json()
    assert [y["year"] for y in r["years"]] == [2026, 2025] and len(r["sales"]) == 5
    y = r["years"][0]
    assert (y["count"], y["no_cost"]) == (4, 1) and Decimal(y["proceeds"]) == Decimal("318")
    assert [Decimal(y[k]) for k in ("gain", "gain_long", "gain_short", "gain_undated")] == [Decimal("73"), Decimal("68"), Decimal("-5"), Decimal("10")]
    only = api.get("/api/v1/reports/sales", params={"year": 2025}).json()["sales"]
    assert len(only) == 1 and only[0]["long_term"] is True and Decimal(only[0]["gain"]) == Decimal("30")
    long_hold = next(s for s in r["sales"] if s["title"] == "Long hold")
    assert Decimal(long_hold["proceeds"]) == Decimal("168") and long_hold["days_held"] == 781
    assert next(s for s in r["sales"] if s["title"] == "No cost")["gain"] is None


def test_qr_code(api):
    r = api.get("/api/v1/reference/qr.svg", params={"text": "http://vault.lan/?location_id=3"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg") and "<svg" in r.text
    assert api.get("/api/v1/reference/qr.svg", params={"text": ""}).status_code == 422


def test_read_only_login(api, client, app):
    item = _create(api, {**EAGLE, "purchase_price": "40"})
    assert api.post("/api/v1/auth/viewers", json={"username": "family", "password": "short"}).status_code == 422
    v = api.post("/api/v1/auth/viewers", json={"username": "family", "password": PASSWORD})
    assert v.status_code == 201 and api.post("/api/v1/auth/viewers", json={"username": "family", "password": PASSWORD}).status_code == 409
    assert [x["username"] for x in api.get("/api/v1/auth/viewers").json()] == ["family"]

    with TestClient(app) as c2:
        viewer = Api(c2)
        me = viewer.login("family").json()
        assert me["read_only"] is True and "items:write" not in me["scopes"] and viewer.get("/api/v1/auth/me").json()["read_only"] is True
        # sees the owner's collection, values and exports
        assert [i["id"] for i in viewer.get("/api/v1/items").json()["items"]] == [item["id"]]
        assert viewer.get(f"/api/v1/items/{item['id']}").json()["title"] == EAGLE["title"]
        assert viewer.get("/api/v1/portfolio/summary").json()["totals"]["item_count"] == 1
        assert "Silver Eagle" in viewer.get("/api/v1/export/items.csv").text
        # and can change nothing
        for method, url, body in [
            ("post", "/api/v1/items", EAGLE), ("patch", f"/api/v1/items/{item['id']}", {"title": "x"}), ("delete", f"/api/v1/items/{item['id']}", None),
            ("post", "/api/v1/items/bulk", {"ids": [item["id"]], "delete": True}), ("post", "/api/v1/wants", {"title": "x"}),
            ("post", "/api/v1/alerts", {"metal": "Ag", "direction": "above", "price": "1"}), ("post", "/api/v1/items/describe", {"text": "x"}),
            ("post", "/api/v1/auth/viewers", {"username": "x", "password": PASSWORD}), ("patch", "/api/v1/settings", {"base_currency": "EUR"}),
            ("post", "/api/v1/auth/tokens", {"name": "t", "scopes": ["items:write"]}),
        ]:
            r = getattr(viewer, method)(url, **({"json": body} if body is not None else {}), headers={"If-Match": "1"})
            assert r.status_code == 403, (method, url, r.status_code, r.text)
        assert viewer.get("/api/v1/auth/viewers").status_code == 403
        assert viewer.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD + "2"}).status_code == 204
        assert viewer.post("/api/v1/auth/logout").status_code == 204
    assert api.get(f"/api/v1/items/{item['id']}").json()["version"] == 1
    vid = v.json()["id"]
    assert api.delete(f"/api/v1/auth/viewers/{vid}").status_code == 204 and api.get("/api/v1/auth/viewers").json() == []
    with TestClient(app) as c3:
        assert Api(c3).login("family", PASSWORD + "2").status_code == 401


CSV = """Title,Qty,Price,Date,Location,Tags,Notes,Grade,Service,Cert,Shoe size
2023 American Silver Eagle,3,$105.00,11/02/2023,Safe > Box A,"stack; eagles",from the show,,,,9
1881-S Morgan Dollar,,85,2025-04-12,Safe > Box A,,,MS63,PCGS,12345678,
10 oz Silver Bar SilverTowne,2,,,,,,,,,
2008 United States 50 State Quarters Silver Proof Set,,42,,,,,,,,
,5,,,,,,,,,
Odd thing,x,,,,,,,,,
1 oz gold bar,1,1900,13/45/2020,,,,,,,
"""


def test_csv_import_previews_then_saves(api):
    files = {"file": ("coins.csv", CSV.encode(), "text/csv")}
    preview = api.post("/api/v1/import/items", files=files).json()
    assert preview["dry_run"] is True and (preview["ok"], preview["failed"], preview["created"]) == (4, 3, 0)
    assert preview["columns_ignored"] == ["Shoe size"] and "Price" in preview["columns_used"]
    rows = {r["line"]: r for r in preview["rows"]}
    assert rows[2]["kind"] == "bullion" and "American Silver Eagle, 1 oz" in rows[2]["summary"] and "×3" in rows[2]["summary"]
    assert "fineness assumed" in rows[4]["summary"] and rows[5]["kind"] == "set"
    assert rows[6]["error"] == "no title" and "not a number" in rows[7]["error"] and "not a date" in rows[8]["error"]
    assert api.get("/api/v1/items").json()["total"] == 0 and api.get("/api/v1/locations").json() == []  # nothing saved

    done = api.post("/api/v1/import/items", params={"dry_run": False}, files=files).json()
    assert (done["ok"], done["failed"], done["created"]) == (4, 3, 4)
    items = {i["title"]: api.get(f"/api/v1/items/{i['id']}").json() for i in api.get("/api/v1/items").json()["items"]}
    eagle = items["2023 American Silver Eagle"]
    assert eagle["quantity"] == 3 and Decimal(eagle["purchase_price"]) == Decimal("105") and eagle["acquired_date"] == "2023-11-02"
    assert eagle["location_path"] == "Safe › Box A" and eagle["tags"] == ["eagles", "stack"] and eagle["notes"] == "from the show"
    assert Decimal(eagle["values"]["pure_toz_total"]["Ag"]) == Decimal("3")
    morgan = items["1881-S Morgan Dollar"]
    assert morgan["condition"]["grading_service"] == "PCGS" and morgan["condition"]["cert_number"] == "12345678" and morgan["condition"]["sheldon_grade"] == 63
    assert morgan["details"]["mint_mark"] == "S" and Decimal(morgan["metal_content"][0]["pure_toz"]) == Decimal("0.773451")
    assert Decimal(items["10 oz Silver Bar SilverTowne"]["values"]["pure_toz_total"]["Ag"]) == Decimal("19.98")
    assert len(items["2008 United States 50 State Quarters Silver Proof Set"]["details"]["coins"]) == 5
    assert len(api.get("/api/v1/locations").json()) == 2  # Safe, and Box A inside it


def test_csv_import_round_trips_the_export(api):
    _spot(Ag="30")
    _create(api, {**EAGLE, "quantity": 2, "purchase_price": "80", "tags": ["a"]})
    _create(api, {"item_type": "coin", "title": "Sold one", "status": "sold", "sale_date": "2026-02-03", "sale_price": "12.50", "purchase_price": "9"})
    exported = api.get("/api/v1/export/items.csv", params={"sort": "title"}).content
    for i in api.get("/api/v1/items").json()["items"]:
        api.delete(f"/api/v1/items/{i['id']}")
    done = api.post("/api/v1/import/items", params={"dry_run": False}, files={"file": ("export.csv", exported, "text/csv")}).json()
    assert (done["created"], done["failed"]) == (2, 0), done["rows"]
    back = {i["title"]: api.get(f"/api/v1/items/{i['id']}").json() for i in api.get("/api/v1/items").json()["items"]}
    assert back["2023 American Silver Eagle"]["quantity"] == 2 and Decimal(back["2023 American Silver Eagle"]["values"]["pure_toz_total"]["Ag"]) == Decimal("2")
    assert back["Sold one"]["status"] == "sold" and back["Sold one"]["sale_date"] == "2026-02-03"
    assert api.post("/api/v1/import/items", files={"file": ("x.csv", b"Name of thing\nfoo\n", "text/csv")}).status_code == 422
