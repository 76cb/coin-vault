"""Metal content from what a title or a scan says, when no reference fits; and base-metal coins not offered silver."""

from decimal import Decimal

import pytest

from app.services.describe import stated_fineness


def _describe(api, text: str) -> dict:
    return api.post("/api/v1/items/describe", json={"text": text}).json()


@pytest.mark.parametrize("text, fineness", [
    ("1 OZ .999 FINE SILVER", "0.999"), ("10 g 999.9", "0.9999"), ("ONE TROY OUNCE 99.99% PURE", "0.9999"),
    ("Sterling silver medal 20 g", "0.925"), ("22K gold", "0.9167"), ("1 oz fine silver", "0.999"),
    ("Feingold 999,9", "0.9999"), ("0.9995 platinum", "0.9995"), ("1999 dollar 999 g", None), ("2021 Morgan", None),
])
def test_stated_fineness(text, fineness):
    assert stated_fineness(text) == (Decimal(fineness) if fineness else None)


@pytest.mark.parametrize("title, metal, grams, fineness, assumed", [
    ("1 Troy Ounce .999 Fine Silver Art Round", "Ag", "31.1035", "0.999", False),
    ("10 oz Silver Bar SilverTowne", "Ag", "311.0348", "0.999", True),
    ("Engelhard 100 oz silver bar", "Ag", "3110.3477", "0.999", True),
    ("1 oz Gold Bar PAMP Suisse Lady Fortuna 999.9", "Au", "31.1035", "0.9999", False),
    ("5 oz Silver Bar", "Ag", "155.5174", "0.999", True),  # no maker: no maker's reference row is offered
    ("1 oz Platinum Bar", "Pt", "31.1035", "0.9995", True),
    ("Sterling silver medal 20 g", "Ag", "20.0000", "0.925", False),
    ("Silver medal 20 g", "Ag", "20.0000", None, False),  # not bullion and no fineness: nothing assumed
])
def test_metal_worked_out_when_no_reference_fits(api, title, metal, grams, fineness, assumed):
    d = _describe(api, title)
    s = d["stamped"]
    assert d["compositions"] == [] and s["metal"] == metal and Decimal(s["gross_weight_g"]) == Decimal(grams)
    assert (Decimal(s["fineness"]) if s["fineness"] else None) == (Decimal(fineness) if fineness else None)
    assert s["fineness_assumed"] is assumed
    assert any(("assumed" in r) == assumed and ("ozt" in r or "fineness not given" in r) for r in d["recognized"][-1:])


def test_a_reference_still_wins(api):
    for title in ("2023 1 oz American Silver Eagle", "Geiger 1 kg silver bar", "1956 D Washington Quarter", "1986 Statue of Liberty Silver Dollar"):
        d = _describe(api, title)
        assert d["compositions"] and d["stamped"] is None, title
    assert _describe(api, "1900 Indian Head Cent")["stamped"] is None  # no metal named, no weight


@pytest.mark.parametrize("title, made_of", [
    ("2000 P Sacagawea Dollar", "Manganese brass"), ("1971 Eisenhower Dollar", "Copper-nickel clad"),
    ("1974 D Eisenhower Dollar", "Copper-nickel clad"), ("1999 Susan B Anthony Dollar", "Copper-nickel clad"),
])
def test_base_metal_dollars_are_not_offered_silver(api, title, made_of):
    d = _describe(api, title)
    assert d["compositions"] == [] and d["details"]["composition"].startswith(made_of)
    assert api.get("/api/v1/compositions/match", params={"country": "United States", "denomination": "$1", "year": d["details"]["year"]}).json() == []


def test_silver_versions_are_still_found(api):
    assert _describe(api, "1976 S Eisenhower Dollar Silver")["compositions"][0]["key"] == "us-ike-40"
    assert _describe(api, "1971-S Eisenhower Dollar")["compositions"][0]["key"] == "us-ike-40"  # only struck in silver
    assert _describe(api, "1943 P Jefferson Nickel")["compositions"][0]["key"] == "us-war-nickel-35"
    assert _describe(api, "1965 Kennedy Half Dollar")["compositions"][0]["key"] == "us-half-40"
    assert _describe(api, "1922 Peace Dollar")["compositions"][0]["key"] == "us-dollar-90"


