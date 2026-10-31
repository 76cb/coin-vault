from decimal import Decimal

from app.compositions_seed import ROWS, ROWS_V1, ROWS_V2, ROWS_V3, _bar, _product


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
    assert ROWS == ROWS_V1 + ROWS_V2 + ROWS_V3
    for r in ROWS_V2 + ROWS_V3:
        assert len(r["key"]) <= 120 and len(r["label"]) <= 200
        assert r["pure_toz"] > 0, r["label"]
        assert r["fineness"] is None or Decimal(0) < r["fineness"] <= 1, r["label"]
        if r["gross_weight_g"] is not None:
            # stated pure content never exceeds gross weight at that fineness by more than rounding
            assert r["pure_toz"] <= r["gross_weight_g"] / Decimal("31.1034768") * r["fineness"] + Decimal("0.0005"), r["label"]


def test_silver_proof_figures():
    by = {r["key"]: r for r in ROWS_V3}
    assert by["us-silver-proof-quarter-90"]["pure_toz"] == Decimal("0.180848")  # 6.25 g x .900
    assert by["us-silver-proof-quarter-999"]["pure_toz"] == Decimal("0.203728")  # 6.343 g x .999
    assert by["us-set-quarters-states"]["pure_toz"] == Decimal("0.904240")  # 5 x 0.180848
    assert by["us-set-silver-1999"]["pure_toz"] == Decimal("1.338275")  # dime + 5 quarters + half
    assert by["us-bicentennial-quarter-40"]["pure_toz"] == Decimal("0.073947")  # 5.75 g x .400
