"""CSV export and the insurance report."""

import csv
import io
from decimal import Decimal

from .test_photos import upload


def _spot(metal, price):
    from app.db import session_factory
    from app.models import SpotPrice, utcnow

    with session_factory()() as db:
        db.add(SpotPrice(metal=metal, currency="USD", price_per_toz=Decimal(price), source="gold_api", fetched_at=utcnow()))
        db.commit()


def _item(api, **body):
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _collection(api):
    _spot("Ag", "30")
    safe = api.post("/api/v1/locations", json={"name": "Safe"}).json()
    morgan = _item(api, item_type="coin", title="1881-S Morgan Dollar", quantity=2, purchase_price="120", acquired_date="2024-05-01",
                   location_id=safe["id"], tags=["morgans"],
                   details={"country": "United States", "denomination": "Dollar", "year": 1881, "mint_mark": "S", "series": "Morgan Dollar"},
                   condition={"grading": "slabbed", "grading_service": "PCGS", "grade_text": "MS65", "cert_number": "12345678"},
                   metal_content=[{"metal": "Ag", "pure_toz": "0.773451"}])
    api.post(f"/api/v1/items/{morgan['id']}/valuations", json={"value_each": "250", "as_of": "2026-10-01", "source": "Dealer quote"})
    bar = _item(api, item_type="bar", title="=HYPERLINK(\"http://x\")", purchase_price="300",
                details={"weight_value": "10", "weight_unit": "ozt", "refiner": "PAMP", "serial_number": "C123456"},
                metal_content=[{"metal": "Ag", "pure_toz": "9.99"}])
    sold = _item(api, item_type="coin", title="Sold dime", metal_content=[{"metal": "Ag", "pure_toz": "0.0723"}])
    api.post(f"/api/v1/items/{sold['id']}/sell", json={"sale_date": "2026-09-01", "sale_price": "3", "sale_venue": "Coin show"})
    gone = _item(api, item_type="coin", title="Deleted one")
    api.delete(f"/api/v1/items/{gone['id']}")
    return morgan, bar, sold


def _rows(text: str) -> list[dict]:
    assert text.startswith("﻿")
    return list(csv.DictReader(io.StringIO(text[1:])))


def test_csv_export(api):
    morgan, bar, sold = _collection(api)
    r = api.get("/api/v1/export/items.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="coinvault-items-' in r.headers["content-disposition"]
    rows = {int(x["ID"]): x for x in _rows(r.text)}
    assert set(rows) == {morgan["id"], bar["id"], sold["id"]}  # sold is in, deleted is not
    m = rows[morgan["id"]]
    assert m["Description"] == "1881-S United States Dollar, Morgan Dollar"
    assert m["Grade"] == "PCGS MS65" and m["Cert number"] == "12345678" and m["Location"] == "Safe" and m["Tags"] == "morgans"
    assert Decimal(m["Silver ozt"]) == Decimal("1.546902") and Decimal(m["Melt value"]) == Decimal("46.41")
    assert Decimal(m["Market value"]) == 500 and Decimal(m["Current value"]) == 500 and m["Market value from"] == "Dealer quote"
    assert m["Value basis"] == "Market value: Dealer quote, Oct 1, 2026" and m["Acquired"] == "2024-05-01"
    b = rows[bar["id"]]
    assert b["Title"].startswith("'=")  # a spreadsheet shows it as text instead of running it
    assert b["Serial number"] == "C123456" and b["Refiner"] == "PAMP" and b["Description"] == "10 ozt, PAMP"
    s = rows[sold["id"]]
    assert s["Status"] == "Sold" and s["Sold through"] == "Coin show" and Decimal(s["Sale price"]) == 3
    only_bars = _rows(api.get("/api/v1/export/items.csv?type=bar").text)
    assert [int(x["ID"]) for x in only_bars] == [bar["id"]]
    assert _rows(api.get("/api/v1/export/items.csv?q=morgan").text)[0]["Title"] == "1881-S Morgan Dollar"


def test_insurance_report(api, images):
    morgan, bar, sold = _collection(api)
    upload(api, morgan["id"], [("o.jpg", images["jpeg"](images["coin"](seed=51)), "image/jpeg"),
                                ("r.jpg", images["jpeg"](images["coin"](seed=52)), "image/jpeg")])
    r = api.get("/api/v1/report")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["owner"] and rep["currency"] == "USD" and rep["count"] == 2 and rep["pieces"] == 3
    assert [i["id"] for i in rep["items"]] == [morgan["id"], bar["id"]]  # highest value first; sold is left out
    assert Decimal(rep["current"]) == Decimal("500") + Decimal("299.70") and Decimal(rep["cost"]) == 420 and rep["unvalued"] == 0
    m = rep["items"][0]
    assert m["identifiers"] == ["PCGS cert 12345678"] and m["grade"] == "PCGS MS65" and Decimal(m["current_each"]) == 250
    assert m["metals"] == "1.546902 ozt silver" and m["location"] == "Safe" and len(m["photos"]) == 2
    assert api.get(m["photos"][0]).status_code == 200
    assert rep["items"][1]["identifiers"] == ["Serial C123456"] and rep["items"][1]["basis"] == "Melt value at spot"
    assert [s["metal"] for s in rep["spot"]] == ["Ag"]
    assert {g["label"]: g["count"] for g in rep["by_location"]} == {"Safe": 1, "No location": 1}
    by_title = api.get("/api/v1/report?order=title").json()["items"]
    assert [i["title"] for i in by_title][0] == "1881-S Morgan Dollar"
    assert api.get("/api/v1/report?status=sold").json()["count"] == 0  # the report is what you hold, whatever the filter
    assert api.get("/api/v1/report?type=bar").json()["count"] == 1
