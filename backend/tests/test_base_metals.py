"""Modern US coins with no precious metal get their composition and weight filled in."""

from decimal import Decimal

import pytest

from app.services.base_metals import lookup


@pytest.mark.parametrize("args, composition, weight", [
    (("United States", "1c", 2025, "D"), "Copper-plated zinc", Decimal("2.5")),
    (("United States", "Cent", 1943, "S"), "Zinc-coated steel", Decimal("2.7")),
    (("USA", "1c", 1960, None), "Bronze", Decimal("3.1")),
    (("United States", "1c", 1982, "D"), "Gilding metal (95% copper) or copper-plated zinc", None),
    (("United States", "5c", 1942, "D"), "Copper-nickel", Decimal("5.000")),
    (("United States", "Quarter", 1965, None), "Copper-nickel clad copper", Decimal("5.670")),
    (("United States", "Half Dollar", 1971, "D"), "Copper-nickel clad copper", Decimal("11.340")),
    (("United States", "$1", 1974, "D"), "Copper-nickel clad copper", Decimal("22.68")),
    (("United States", "$1", 1979, "P"), "Copper-nickel clad copper", Decimal("8.1")),
    (("United States", "$1", 2000, "P"), "Manganese brass", Decimal("8.1")),
])
def test_lookup(args, composition, weight):
    hit = lookup(*args)
    assert hit is not None and hit.composition.startswith(composition) and hit.weight_g == weight


@pytest.mark.parametrize("args", [
    ("United States", "25c", 1964, None),  # 90% silver
    ("United States", "50c", 1967, None),  # 40% silver
    ("United States", "5c", 1943, "P"),  # wartime silver
    ("United States", "5c", 1942, "S"),
    ("Canada", "25c", 2000, None),
    ("United States", "1c", None, None),
])
def test_no_entry_for_silver_or_other_countries(args):
    assert lookup(*args) is None


def test_filled_in_on_new_and_edited_coins(api):
    item = api.post("/api/v1/items", json={"item_type": "coin", "title": "2025 D Cent",
                                            "details": {"country": "United States", "denomination": "1c", "year": 2025}}).json()
    assert item["details"]["composition"].startswith("Copper-plated zinc") and float(item["details"]["weight_g"]) == 2.5
    # an item whose details are filled in later
    blank = api.post("/api/v1/items", json={"item_type": "coin", "title": "Quarter"}).json()
    assert blank["details"]["composition"] is None
    r = api.patch(f"/api/v1/items/{blank['id']}", json={"details": {"country": "United States", "denomination": "25c", "year": 1999}},
                  headers={"If-Match": str(blank["version"])})
    assert r.status_code == 200 and r.json()["details"]["composition"].startswith("Copper-nickel clad")
    # one with silver recorded is left alone
    silver = api.post("/api/v1/items", json={"item_type": "coin", "title": "1976-S Silver Quarter",
                                             "details": {"country": "United States", "denomination": "25c", "year": 1976},
                                             "metal_content": [{"metal": "Ag", "gross_weight_g": "5.75", "fineness": "0.4"}]}).json()
    assert silver["details"]["composition"] is None
    # typed in by the owner: kept
    own = api.post("/api/v1/items", json={"item_type": "coin", "title": "Odd cent", "details": {
        "country": "United States", "denomination": "1c", "year": 2025, "composition": "Off-metal error, on a dime planchet"}}).json()
    assert own["details"]["composition"] == "Off-metal error, on a dime planchet"


def test_title_reader_fills_it_for_the_form(api):
    d = api.post("/api/v1/items/describe", json={"text": "2025 D Lincoln Cent"}).json()
    assert d["details"]["composition"].startswith("Copper-plated zinc") and d["details"]["weight_g"] == "2.5"
    assert "no precious metal" in d["recognized"]
    d = api.post("/api/v1/items/describe", json={"text": "1964 Washington Quarter"}).json()
    assert "composition" not in d["details"] and d["compositions"]  # silver: the reference row instead
