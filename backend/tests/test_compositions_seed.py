from decimal import Decimal

from app.compositions_seed import (
    CATALOGUE_DIR, CATALOGUE_V4, CATALOGUE_V5, ROWS, ROWS_V1, ROWS_V2, ROWS_V3, ROWS_V4, ROWS_V5, _bar, _catalogue_row, _product,
)


def test_bar_math_and_labels():
    kilo = _bar("Valcambi", "Ag", "1 kg", "0.999", "src")
    assert kilo["label"] == "Valcambi silver bar, 1 kg (.999)" and kilo["denomination"] == "bar"
    assert kilo["pure_toz"] == Decimal("32.118596")  # 1000 g / 31.1034768 x 0.999
    oz = _bar("PAMP Suisse", "Au", "1 oz", "0.9999", "src")
    assert oz["gross_weight_g"] == Decimal("31.1035") and oz["pure_toz"] == Decimal("0.999900")
    half = _bar("Perth Mint", "Au", "1/2 oz", "0.9999", "src")
    assert half["pure_toz"] == Decimal("0.499950")
    assert _bar("Royal Canadian Mint", "Ag", "10 oz", "0.9999", "s")["key"] == "bar-royal-canadian-mint-ag-10-oz-9999"
    assert _product("Valcambi Silver CombiBar 100 g", "Ag", "100", "0.999", "s")["pure_toz"] == Decimal("3.211860")


def test_seed_rows_are_consistent():
    keys = [r["key"] for r in ROWS]
    assert len(keys) == len(set(keys)), "duplicate keys"
    assert ROWS[: len(ROWS_V1)] == ROWS_V1
    assert ROWS == ROWS_V1 + ROWS_V2 + ROWS_V3 + ROWS_V4 + ROWS_V5
    # every catalogue file is loaded by exactly one migration
    files = CATALOGUE_V4 + CATALOGUE_V5
    assert sorted(files) == sorted(p.name for p in CATALOGUE_DIR.glob("*.json")) and len(files) == len(set(files))
    for r in ROWS_V2 + ROWS_V3 + ROWS_V4 + ROWS_V5:
        assert len(r["key"]) <= 120 and len(r["label"]) <= 200
        assert r["pure_toz"] > 0, r["label"]
        assert r["fineness"] is None or Decimal(0) < r["fineness"] <= 1, r["label"]
        if r["gross_weight_g"] is not None:
            # stated pure content never exceeds gross weight at that fineness by more than rounding
            # (catalogue sources round gross weights, so allow 0.5% there)
            slack = r["pure_toz"] * Decimal("0.005") if r["key"].startswith("cat-") else Decimal("0.0005")
            assert r["pure_toz"] <= r["gross_weight_g"] / Decimal("31.1034768") * r["fineness"] + slack, r["label"]


def test_silver_proof_figures():
    by = {r["key"]: r for r in ROWS_V3}
    assert by["us-silver-proof-quarter-90"]["pure_toz"] == Decimal("0.180848")  # 6.25 g x .900
    assert by["us-silver-proof-quarter-999"]["pure_toz"] == Decimal("0.203728")  # 6.343 g x .999
    assert by["us-set-quarters-states"]["pure_toz"] == Decimal("0.904240")  # 5 x 0.180848
    assert by["us-set-silver-1999"]["pure_toz"] == Decimal("1.338275")  # dime + 5 quarters + half
    assert by["us-bicentennial-quarter-40"]["pure_toz"] == Decimal("0.073947")  # 5.75 g x .400


def test_world_catalogue():
    assert len(ROWS_V4) > 250
    countries = {r["country"] for r in ROWS_V4}
    assert {"United Kingdom", "Canada", "Mexico", "China", "Australia", "Japan"} <= countries
    assert all(r["key"].startswith("cat-") and r["citation"].startswith("http") for r in ROWS_V4)
    for r in ROWS_V4:
        assert r["metal"] in {"Au", "Ag", "Pt", "Pd"}, r["label"]
        if r["year_from"] and r["year_to"]:
            assert r["year_from"] <= r["year_to"], r["label"]
    # no new row repeats a coin we already had (same country, metal, content and years)
    older = [r for r in ROWS_V1 + ROWS_V2 + ROWS_V3 if r["country"]]
    for r in ROWS_V4 + ROWS_V5:
        for o in older:
            same = (o["country"], o["metal"], o["year_from"], o["year_to"]) == (r["country"], r["metal"], r["year_from"], r["year_to"])
            assert not (same and abs(o["pure_toz"] - r["pure_toz"]) < Decimal("0.001")), (r["label"], o["label"])


def test_catalogue_row_math():
    row = _catalogue_row({"country": "Great Britain", "denomination": "(none listed)", "label": "Great Britain crown",
                          "year_from": 1902, "year_to": 1919, "metal": "Ag", "gross_g": "28.2759", "fineness": "0.925",
                          "pure_toz": None, "source": "https://example.org/crown", "note": "Sterling."})
    assert row["country"] == "United Kingdom" and row["denomination"] is None
    assert row["key"] == "cat-united-kingdom-great-britain-crown"
    assert row["pure_toz"] == Decimal("0.840909")  # 28.2759 g / 31.1034768 x .925
    assert row["citation"] == "https://example.org/crown. Sterling."
    stated = _catalogue_row({"country": "Australia", "denomination": "1 Dollar", "label": "Australia 1 oz",
                             "year_from": None, "year_to": None, "metal": "Ag", "gross_g": None, "fineness": "0.9999",
                             "pure_toz": "1", "source": "https://example.org", "note": ""})
    assert stated["pure_toz"] == Decimal("1.000000") and stated["gross_weight_g"] is None and stated["label"] == "Australia 1 oz"
    assert stated["key"] == "cat-australia-1-oz"
