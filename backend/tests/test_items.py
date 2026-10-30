from decimal import Decimal

from tests.conftest import Api

MORGAN = {
    "item_type": "coin",
    "title": "1881-S Morgan Dollar",
    "quantity": 1,
    "acquired_date": "2025-04-12",
    "purchase_price": "85.00",
    "purchase_fees": "6.50",
    "purchase_source": "Local coin show",
    "condition": {"grading": "slabbed", "grading_service": "PCGS", "sheldon_grade": 63, "grade_text": "MS63", "cert_number": "12345678", "designations": ["CAC"]},
    "details": {"country": "United States", "denomination": "$1", "year": 1881, "mint_mark": "S", "series": "Morgan Dollar", "pcgs_number": "7126"},
    "metal_content": [{"metal": "Ag", "gross_weight_g": "26.73", "fineness": "0.9"}],
    "tags": ["Morgans", "slabbed"],
}


def create(api: Api, body: dict) -> dict:
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_read_coin(api):
    item = create(api, MORGAN)
    assert item["details"]["mint_mark"] == "S" and item["details"]["year"] == 1881
    assert Decimal(item["cost_basis"]) == Decimal("91.50")
    assert item["cost_basis_status"] == "known"
    assert item["condition"]["grading_service"] == "PCGS" and item["condition"]["designations"] == ["CAC"]
    # 26.73 g / 31.1034768 * 0.9 = 0.773451 ozt (the Morgan ASW)
    assert Decimal(item["metal_content"][0]["pure_toz"]) == Decimal("0.773451")
    assert item["metal_content"][0]["source"] == "computed"
    assert sorted(item["tags"]) == ["Morgans", "slabbed"]
    assert api.get(f"/api/v1/items/{item['id']}").json()["title"] == MORGAN["title"]


def test_all_six_types(api):
    bodies = [
        {"item_type": "bullion", "title": "2024 American Silver Eagle", "details": {"product_line": "American Silver Eagle", "year": 2024, "mint": "US Mint"}, "metal_content": [{"metal": "Ag", "gross_weight_g": "31.103", "fineness": "0.999"}]},
        {"item_type": "bar", "title": "10 oz Silver Bar", "details": {"weight_value": "10", "weight_unit": "ozt", "refiner": "PAMP", "serial_number": "A123", "has_assay_card": True}, "metal_content": [{"metal": "Ag", "fineness": "0.999"}]},
        {"item_type": "banknote", "title": "1957 $1 Silver Certificate", "details": {"country": "United States", "denomination": "$1", "series": "1957", "serial_number": "A12345678A", "pick_number": "419"}},
        {"item_type": "lot", "title": "90% dimes", "details": {"face_value": "12.50", "face_currency": "USD"}},
        {"item_type": "other", "title": "Gold ring scrap", "details": {"attributes": {"karat": "14k", "stamp": "585"}}, "metal_content": [{"metal": "Au", "gross_weight_g": "4.2", "fineness": "0.585"}]},
    ]
    for b in bodies:
        item = create(api, b)
        assert item["item_type"] == b["item_type"]
    page = api.get("/api/v1/items").json()
    assert page["total"] == 5


def test_bar_derives_gross_weight_from_unit(api):
    bar = create(api, {"item_type": "bar", "title": "1 kg silver", "details": {"weight_value": "1", "weight_unit": "kg"}, "metal_content": [{"metal": "Ag", "fineness": "0.999"}]})
    mc = bar["metal_content"][0]
    assert Decimal(mc["gross_weight_g"]) == Decimal("1000")
    assert Decimal(mc["pure_toz"]) == Decimal("32.118596")  # 1000 / 31.1034768 * 0.999
    tola = create(api, {"item_type": "bar", "title": "10 tola gold", "details": {"weight_value": "10", "weight_unit": "tola"}, "metal_content": [{"metal": "Au", "fineness": "0.999"}]})
    assert Decimal(tola["metal_content"][0]["gross_weight_g"]) == Decimal("116.638038")


def test_override_pure_weight(api):
    item = create(api, {"item_type": "coin", "title": "Override", "metal_content": [{"metal": "Ag", "gross_weight_g": "12.5", "fineness": "0.9", "pure_toz": "0.36169"}]})
    assert item["metal_content"][0]["source"] == "override"
    assert Decimal(item["metal_content"][0]["pure_toz"]) == Decimal("0.36169")


def test_validation_errors(api):
    assert api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "details": {"year": "not a year"}}).status_code == 422
    assert api.post("/api/v1/items", json={"item_type": "bar", "title": "x", "details": {"weight_unit": "pound"}}).status_code == 422
    assert api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "condition": {"grading": "raw", "cert_number": "1"}}).status_code == 422
    assert api.post("/api/v1/items", json={"item_type": "spaceship", "title": "x"}).status_code == 422
    assert api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "quantity": 0}).status_code == 422
    assert api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "status": "sold"}).status_code == 422
    assert api.post("/api/v1/items", json={"item_type": "coin", "title": "x", "metal_content": [{"metal": "Ag", "fineness": "1.5"}]}).status_code == 422


def test_cost_basis_optional_and_status(api):
    unknown = create(api, {"item_type": "coin", "title": "Inherited"})
    assert unknown["cost_basis"] is None and unknown["cost_basis_status"] == "unknown"
    est = create(api, {"item_type": "coin", "title": "Gift", "purchase_price": "20", "cost_basis_status": "estimated"})
    assert est["cost_basis_status"] == "estimated"
    r = api.patch(f"/api/v1/items/{unknown['id']}", json={"purchase_price": "40"}, headers={"If-Match": str(unknown["version"])})
    assert r.json()["cost_basis_status"] == "known"
    r2 = api.patch(f"/api/v1/items/{unknown['id']}", json={"purchase_price": None}, headers={"If-Match": str(r.json()["version"])})
    assert r2.json()["cost_basis_status"] == "unknown" and r2.json()["cost_basis"] is None


def test_patch_requires_matching_version(api):
    item = create(api, MORGAN)
    url = f"/api/v1/items/{item['id']}"
    assert api.patch(url, json={"title": "x"}).status_code == 428
    assert api.patch(url, json={"title": "x"}, headers={"If-Match": "999"}).status_code == 412
    r = api.patch(url, json={"title": "Renamed", "details": {"variety_notes": "VAM-2"}}, headers={"If-Match": str(item["version"])})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Renamed" and body["version"] == item["version"] + 1
    assert body["details"]["variety_notes"] == "VAM-2" and body["details"]["mint_mark"] == "S"  # merged, not replaced
    assert api.patch(url, json={"title": "stale"}, headers={"If-Match": str(item["version"])}).status_code == 412
    assert api.patch(url, json={"title": None}, headers={"If-Match": str(body["version"])}).status_code == 422


def test_type_change_replaces_details(api):
    item = create(api, {"item_type": "coin", "title": "Was a coin", "details": {"year": 1900}})
    r = api.patch(f"/api/v1/items/{item['id']}", json={"item_type": "bar", "details": {"weight_value": "1"}}, headers={"If-Match": "1"})
    assert r.status_code == 200
    assert Decimal(r.json()["details"]["weight_value"]) == 1 and "year" not in r.json()["details"]


def test_audit_log_records_value_fields(api):
    item = create(api, MORGAN)
    api.patch(f"/api/v1/items/{item['id']}", json={"purchase_price": "90", "notes": "not audited"}, headers={"If-Match": "1"})
    api.post(f"/api/v1/items/{item['id']}/sell", json={"sale_date": "2026-10-01", "sale_price": "140", "sale_fees": "18.2", "sale_venue": "eBay"})
    audit = api.get(f"/api/v1/items/{item['id']}/audit").json()
    fields = [e["field"] for e in audit]
    assert "purchase_price" in fields and "status" in fields and "sale_price" in fields
    assert "notes" not in fields
    price = next(e for e in audit if e["field"] == "purchase_price" and e["old_value"] == "85")
    assert price["new_value"] == "90"
    assert api.get(f"/api/v1/items/{item['id']}").json()["status"] == "sold"


def test_list_filters_and_search(api):
    loc = api.post("/api/v1/locations", json={"name": "Safe"}).json()
    create(api, {**MORGAN, "location_id": loc["id"]})
    create(api, {"item_type": "bar", "title": "Gold bar", "metal_content": [{"metal": "Au", "gross_weight_g": "31.1", "fineness": "0.9999"}]})
    create(api, {"item_type": "banknote", "title": "Note", "details": {"serial_number": "B987"}})
    get = lambda qs: api.get(f"/api/v1/items?{qs}").json()  # noqa: E731
    assert get("type=bar")["total"] == 1
    assert get("metal=Ag")["items"][0]["title"].startswith("1881")
    assert get("metal=Au")["total"] == 1
    assert get("q=morgan")["total"] == 1
    assert get("q=1881")["total"] == 1
    assert get("q=B987")["total"] == 1
    assert get("q=12345678")["total"] == 1  # cert number
    assert get("tag=morgans")["total"] == 1
    assert get(f"location_id={loc['id']}")["total"] == 1
    entry = get("type=coin")["items"][0]
    assert entry["grade"] == "PCGS MS63 CAC" and entry["year"] == 1881 and entry["location_path"] == "Safe"
    assert get("page_size=1&page=2")["items"][0]["id"]


def test_soft_delete_and_restore(api):
    item = create(api, MORGAN)
    assert api.delete(f"/api/v1/items/{item['id']}").status_code == 204
    assert api.get("/api/v1/items").json()["total"] == 0
    assert api.get("/api/v1/items?deleted=true").json()["total"] == 1
    assert api.post(f"/api/v1/items/{item['id']}/restore").status_code == 200
    assert api.get("/api/v1/items").json()["total"] == 1


def test_owner_isolation(app, api, make_user):
    from fastapi.testclient import TestClient

    item = create(api, MORGAN)
    make_user("second", admin=False)
    with TestClient(app) as c2:
        other = Api(c2)
        assert other.login("second").status_code == 200
        assert other.get(f"/api/v1/items/{item['id']}").status_code == 404
        assert other.get("/api/v1/items").json()["total"] == 0
        assert other.patch(f"/api/v1/items/{item['id']}", json={"title": "x"}, headers={"If-Match": "1"}).status_code == 404


def test_locations_tree_and_tags(api):
    safe = api.post("/api/v1/locations", json={"name": "Safe"}).json()
    drawer = api.post("/api/v1/locations", json={"name": "Drawer 2", "parent_id": safe["id"]}).json()
    box = api.post("/api/v1/locations", json={"name": "Box A", "parent_id": drawer["id"]}).json()
    assert box["path"] == "Safe › Drawer 2 › Box A"
    # A location cannot be moved inside its own descendant.
    assert api.patch(f"/api/v1/locations/{safe['id']}", json={"name": "Safe", "parent_id": box["id"]}).status_code == 422
    item = create(api, {"item_type": "coin", "title": "Stored", "location_id": box["id"]})
    assert item["location_path"] == "Safe › Drawer 2 › Box A"
    assert api.delete(f"/api/v1/locations/{box['id']}").status_code == 409
    tags = api.get("/api/v1/tags").json()
    assert tags == []
    create(api, {"item_type": "coin", "title": "Tagged", "tags": ["Key date", "key DATE", "Toned"]})
    names = [t["name"] for t in api.get("/api/v1/tags").json()]
    assert names == ["Key date", "Toned"]
