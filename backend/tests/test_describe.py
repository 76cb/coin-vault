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



def test_users_silver_proofs(api):
    q = api.post("/api/v1/items/describe", json={"text": "2015-S 25C PCGS PR70DCAM Bombay Hook NP - Silver First Strike"}).json()
    assert q["condition"]["grade_text"] == "PR70" and q["condition"]["designations"] == ["DCAM", "First Strike"]
    assert q["details"]["series"] == "America the Beautiful" and q["details"]["denomination"] == "25c"
    assert [c["key"] for c in q["compositions"]][:1] == ["us-silver-proof-quarter-90"]
    own = api.post("/api/v1/items/describe", json={"text": "2015 first strike SILVER QUARTER PR70 BOMBAY HOOK NP"}).json()
    assert own["compositions"][0]["key"] == "us-silver-proof-quarter-90"
    new = api.post("/api/v1/items/describe", json={"text": "2022-S American Women Silver Proof Quarter"}).json()
    assert new["compositions"][0]["key"] == "us-silver-proof-quarter-999"
    clad = api.post("/api/v1/items/describe", json={"text": "2015-S Bombay Hook NP Proof Quarter PR69 DCAM"}).json()
    assert all(not c["key"].startswith("us-silver-proof") for c in clad["compositions"])  # no "silver": copper-nickel
    s = api.post("/api/v1/items/describe", json={"text": "2008-S State Quarters Silver Proof Set- with box & certificate of authenticity"}).json()
    assert s["compositions"][0]["key"] == "us-set-quarters-states" and s["notes"] == ["Original government packaging with certificate"]
    full = api.post("/api/v1/items/describe", json={"text": "2012 S Silver Proof Set OGP"}).json()
    assert full["compositions"][0]["key"] == "us-set-silver-1999"
    bicent = api.post("/api/v1/items/describe", json={"text": "1976-S Bicentennial Silver Quarter 40% proof"}).json()
    assert bicent["compositions"][0]["key"] == "us-bicentennial-quarter-40"
    old = api.post("/api/v1/items/describe", json={"text": "1942 S Washington Silver Quarter"}).json()
    assert old["compositions"][0]["key"] == "us-quarter-90"


def test_production_abbreviations():
    from app.services.describe import describe

    d = describe("2021 $1 Silver Eagle T1 Last Day Prod PCGS MS70 Legends of Life Robert Brazile")
    assert "Last Day of Production" in d.condition["designations"] and d.condition["grade_text"] == "MS70"
    assert "First Production" in describe("2021 ASE T2 First Prod. NGC MS69").condition["designations"]


def test_a_bare_us_denomination_is_a_us_coin_with_its_series():
    from app.services.describe import describe

    d = describe("1956 Quarter")
    assert d.details["country"] == "United States" and d.details["series"] == "Washington" and d.details["denomination"] == "25c"
    assert describe("1943 Penny").details["series"] == "Lincoln Wheat"
    assert describe("1964 half dollar").details["series"] == "Kennedy"
    assert describe("2005 quarter").details["series"] == "50 State Quarters"
    # years where two designs were struck: the country, but no guess at the series
    for title in ("1921 silver dollar", "1909 cent", "1976 quarter"):
        d = describe(title)
        assert d.details["country"] == "United States" and "series" not in d.details, title
    # another country named: left alone
    d = describe("1956 Canada Quarter")
    assert d.details["country"] == "Canada" and "series" not in d.details


def test_bare_quarter_still_finds_its_silver(api):
    r = api.post("/api/v1/items/describe", json={"text": "1956 Quarter"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["details"]["country"] == "United States"
    m = api.get("/api/v1/compositions/match", params={k: v for k, v in body["details"].items() if k in ("country", "denomination", "year", "series")}).json()
    assert m[0]["key"] == "us-quarter-90"


@pytest.mark.parametrize("text, metal, label", [
    ("2027P Australia G$5 Year of the Goat NGC MS 69", "Au", "Perth Lunar III gold 1/20 oz"),
    ("2026P Australia Pt $15 Year of the Horse NGC MS70", "Pt", "Australian Lunar Series III Platinum 1/10 oz (.9995)"),
    ("2026 Australia 1 oz Platinum Lunar Horse BU", "Pt", "Australian Lunar Series III Platinum 1 oz (.9995)"),
    ("2026 Australia Year of the Horse 1/2 oz silver", "Ag", "Australian Lunar Series III Silver 1/2 oz (.9999)"),
    ("2021 Australia Kangaroo $15 gold", "Au", "Gold Kangaroo (Nugget) 1/10 oz"),
])
def test_lunar_and_ngc_metal_prefix_find_the_right_size(api, text, metal, label):
    d = api.post("/api/v1/items/describe", json={"text": text}).json()
    assert d["item_type"] == "bullion" and d["metal"] == metal and d["details"]["country"] == "Australia"
    assert d["compositions"] and d["compositions"][0]["label"] == label, [c["label"] for c in d["compositions"]]


def test_metal_symbols_and_ngc_prefixes():
    assert describe("1 oz 9999 Ag round").metal == "Ag"
    assert describe("2024 Canada S$5 Maple Leaf").metal == "Ag"
    assert describe("1881-S Morgan $1 AU58").metal is None  # AU is a grade, not gold
    d = describe("2027P Australia G$5 Year of the Goat NGC MS 69")
    assert d.details["denomination"] == "$5" and d.details["mint_mark"] == "P" and d.condition["grade_text"] == "MS69"
