from decimal import Decimal

from app.compositions_seed import ROWS, ROWS_V1, ROWS_V2, _bar, _product


def test_bar_math_and_labels():
    kilo = _bar("Valcambi", "Ag", "1 kg", "0.999", "src")
    assert kilo["label"] == "Valcambi silver bar, 1 kg (.999)" and kilo["denomination"] == "bar"
    assert kilo["pure_toz"] == Decimal("32.118596")  # 1000 g / 31.1034768 x 0.999
    oz = _bar("PAMP Suisse", "Au", "1 oz", "0.9999", "src")
    assert oz["gross_weight_g"] == Decimal("31.1035") and oz["pure_toz"] == Decimal("0.999900")
    half = _bar("Perth Mint", "Au", "1/2 oz", "0.9999", "src")
    assert half["pure_toz"] == Decimal("0.499950")
    assert _bar("Royal Canadian Mint", "Ag", "10 oz", "0.9999", "s")["key"] == "bar-royal-canadian-mint-ag-10-oz"
    assert _product("Valcambi Silver CombiBar 100 g", "Ag", "100", "0.999", "s")["pure_toz"] == Decimal("3.211860")


def test_seed_rows_are_consistent():
    keys = [r["key"] for r in ROWS]
    assert len(keys) == len(set(keys)), "duplicate keys"
    assert ROWS[: len(ROWS_V1)] == ROWS_V1
    for r in ROWS_V2:
        assert len(r["key"]) <= 120 and len(r["label"]) <= 200
        assert Decimal(0) < r["fineness"] <= 1 and r["pure_toz"] > 0, r["label"]
        if r["gross_weight_g"] is not None:
            # stated pure content never exceeds gross weight at that fineness by more than rounding
            assert r["pure_toz"] <= r["gross_weight_g"] / Decimal("31.1034768") * r["fineness"] + Decimal("0.0005"), r["label"]
