import pytest

from app.services.describe import describe


def test_users_silver_eagle_listing():
    d = describe("2021 $1 Silver Eagle T2 First Production PCGS MS70 Legends Life Robert Brazile")
    assert d.item_type == "bullion" and d.metal == "Ag" and d.composition_key == "ase-1oz"
    assert d.details == {"year": 2021, "denomination": "$1", "country": "United States",
                         "product_line": "American Silver Eagle", "variety_notes": "Type 2"}
    assert d.condition["grading"] == "slabbed" and d.condition["grading_service"] == "PCGS"
    assert d.condition["grade_text"] == "MS70" and d.condition["sheldon_grade"] == 70
    assert d.condition["designations"] == ["First Production"]
    assert d.title.startswith("2021 $1 Silver Eagle")


@pytest.mark.parametrize("text, expect", [
    ("1881-S Morgan Dollar NGC MS63 CAC", {"item_type": "coin", "series": "Morgan", "denomination": "$1", "year": 1881, "mint_mark": "S", "grade": "MS63", "designations": ["CAC"]}),
    ("1964 D Washington quarter VF20", {"item_type": "coin", "denomination": "25c", "mint_mark": "D", "grading": "raw", "grade": "VF20"}),
    ("2023 1/10 oz Gold Eagle BU", {"item_type": "bullion", "key": "age-tenth"}),
    ("1oz Silver Maple Leaf 2024", {"item_type": "bullion", "key": "maple-ag-1oz", "country": "Canada"}),
    ("Gold Maple Leaf 1 oz", {"item_type": "bullion", "key": "maple-au-1oz"}),
    ("100x 1 gram Silver Bar Valcambi CombiBar with assay", {"item_type": "bar", "refiner": "Valcambi", "weight": ("100", "g"), "metal": "Ag"}),
    ("PAMP 1 oz Gold Bar Fortuna", {"item_type": "bar", "refiner": "PAMP Suisse", "weight": ("1", "ozt"), "metal": "Au"}),
    ("1 kilo silver bar", {"item_type": "bar", "weight": ("1", "kg")}),
    ("1957 $1 Silver Certificate PMG 64 EPQ", {"item_type": "banknote", "series": "1957", "grade": "64 EPQ", "metal": None}),
    ("$10 face 90% junk silver dimes", {"item_type": "lot", "key": "us-90-per-face", "face": "10"}),
    ("Lot of 20 1964 Kennedy Half Dollars", {"item_type": "coin", "quantity": 20, "denomination": "50c"}),
    ("ASE 2024 1 oz", {"item_type": "bullion", "key": "ase-1oz"}),
    ("Gilded age token", {"item_type": "other"}),
    ("base metal coin", {"item_type": "other"}),
])
def test_titles(text, expect):
    d = describe(text)
    assert d.item_type == expect["item_type"]
    if "key" in expect:
        assert d.composition_key == expect["key"]
    for f in ("series", "denomination", "year", "mint_mark", "refiner", "country"):
        if f in expect:
            assert d.details.get(f) == expect[f], f
    if "grade" in expect:
        assert d.condition["grade_text"] == expect["grade"]
    if "grading" in expect:
        assert d.condition["grading"] == expect["grading"]
    if "designations" in expect:
        assert d.condition["designations"] == expect["designations"]
    if "weight" in expect:
        assert (d.details["weight_value"], d.details["weight_unit"]) == expect["weight"]
    if "metal" in expect:
        assert d.metal == expect["metal"]
    if "quantity" in expect:
        assert d.quantity == expect["quantity"]
    if "face" in expect:
        assert d.details["face_value"] == expect["face"]


def test_describe_endpoint_suggests_reference(api):
    r = api.post("/api/v1/items/describe", json={"text": "2021 $1 Silver Eagle T2 First Production PCGS MS70"}).json()
    assert r["item_type"] == "bullion" and [c["key"] for c in r["compositions"]] == ["ase-1oz"]
    assert "American Silver Eagle" in r["recognized"]
    morgan = api.post("/api/v1/items/describe", json={"text": "1881-S Morgan Dollar NGC MS63"}).json()
    assert morgan["compositions"][0]["key"] == "us-dollar-90"
    # nothing is saved
    assert api.get("/api/v1/items").json()["total"] == 0


@pytest.mark.parametrize("text, key", [
    ("2023 1/4 oz Gold Maple Leaf", "maple-au-quarter"),
    ("1 oz Gold Maple Leaf", "maple-au-1oz"),
    ("2022 Half Sovereign gold", "sovereign-half"),
    ("Gold Sovereign Elizabeth II", "sovereign-full"),
    ("2024 Australian Kookaburra 1oz silver", "kookaburra-ag-1oz"),
    ("2023 1 oz Gold Kangaroo", "kangaroo-au-1oz"),
    ("1915 Austria 100 Corona restrike", "corona-100-au"),
])
def test_more_bullion(text, key):
    assert describe(text).composition_key == key


def test_bars_match_the_reference(api):
    combi = api.post("/api/v1/items/describe", json={"text": "100x 1 gram Silver Bar Valcambi CombiBar"}).json()
    assert combi["item_type"] == "bar" and combi["compositions"][0]["label"] == "Valcambi Silver CombiBar 100 x 1 g"
    plain = api.post("/api/v1/items/describe", json={"text": "Valcambi 100 gram silver bar"}).json()
    assert plain["compositions"][0]["label"] == "Valcambi silver bar, 100 g (.999)"
    pamp = api.post("/api/v1/items/describe", json={"text": "PAMP Suisse 10 gram gold bar Fortuna"}).json()
    assert pamp["compositions"][0]["label"] == "PAMP Suisse gold bar, 10 g (.9999)"
    kilo = api.post("/api/v1/items/describe", json={"text": "Heraeus 1 kilo silver bar"}).json()
    assert kilo["compositions"][0]["label"] == "Heraeus silver bar, 1 kg (.9999)"
    unknown = api.post("/api/v1/items/describe", json={"text": "Engelhard 10 oz silver bar"}).json()
    assert unknown["item_type"] == "bar" and unknown["compositions"] == []  # Engelhard isn't in the verified list


def test_label_and_metal_aware_match(api):
    d = describe("2021 $1 Silver Eagle T2 First Production PCGS MS70 Legends Life Robert Brazile")
    assert d.notes == ["Label: Legends of Life"]
    keys = [c["key"] for c in api.get("/api/v1/compositions/match", params={
        "country": "United States", "denomination": "$1", "year": 2021, "series": "American Silver Eagle"}).json()]
    assert keys and all(not k.startswith(("age-", "buffalo")) for k in keys)
