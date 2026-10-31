"""Melt and valuation math with fixed spot prices."""

from decimal import Decimal

from sqlalchemy import select

SPOT = {"Au": Decimal("4000"), "Ag": Decimal("30"), "Pt": Decimal("1500"), "Pd": Decimal("1000")}


def create(api, body):
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def comp_id(key):
    from app.db import session_factory
    from app.models import Composition

    with session_factory()() as db:
        return db.scalar(select(Composition.id).where(Composition.key == key))


def values(item_id):
    from app.db import session_factory
    from app.models import Item
    from app.services.valuation import item_values

    with session_factory()() as db:
        return item_values(db, db.get(Item, item_id), SPOT)


def test_morgan_melt_from_reference_composition(api):
    item = create(api, {"item_type": "coin", "title": "Morgans", "quantity": 3, "purchase_price": "120",
                        "metal_content": [{"metal": "Ag", "composition_id": comp_id("us-dollar-90")}]})
    mc = item["metal_content"][0]
    assert mc["source"] == "reference" and Decimal(mc["pure_toz"]) == Decimal("0.773451")
    v = values(item["id"])
    # 3 x 0.773451 ozt x $30 = $69.61059
    assert v.melt == Decimal("69.61") and v.current == Decimal("69.61") and v.rule_applied == "melt"
    assert v.cost == Decimal("120.00") and v.gain == Decimal("-50.39")


def test_bar_lot_and_mixed_metals(api):
    bar = create(api, {"item_type": "bar", "title": "1 kg", "details": {"weight_value": "1", "weight_unit": "kg"},
                       "metal_content": [{"metal": "Ag", "fineness": "0.999"}]})
    assert values(bar["id"]).melt == Decimal("963.56")  # 32.118596 ozt x $30
    lot = create(api, {"item_type": "lot", "title": "$12.50 face 90%",
                       "details": {"face_value": "12.50", "composition_id": comp_id("us-90-per-face")}})
    v = values(lot["id"])
    assert v.pure_toz_per_unit == {"Ag": Decimal("12.50") * Decimal("0.723392")}
    assert v.melt == Decimal("271.27")  # 9.0424 ozt x $30
    worn = create(api, {"item_type": "lot", "title": "worn", "details": {"face_value": "10", "composition_id": comp_id("us-90-per-face-worn")}})
    assert values(worn["id"]).melt == Decimal("214.50")  # 10 x 0.715 x $30
    scrap = create(api, {"item_type": "other", "title": "Ring", "metal_content": [
        {"metal": "Au", "gross_weight_g": "3.11034768", "fineness": "0.5"},
        {"metal": "Ag", "gross_weight_g": "31.1034768", "fineness": "1"}]})
    v = values(scrap["id"])
    assert v.melt_by_metal == {"Au": Decimal("200.00"), "Ag": Decimal("30.00")} and v.melt == Decimal("230.00")


def test_missing_spot_and_rules(api):
    from app.db import session_factory
    from app.models import Item
    from app.services.valuation import item_values

    item = create(api, {"item_type": "bullion", "title": "Pt + Ag", "purchase_price": "10", "metal_content": [
        {"metal": "Pt", "pure_toz": "1"}, {"metal": "Ag", "pure_toz": "1"}]})
    with session_factory()() as db:
        it = db.get(Item, item["id"])
        v = item_values(db, it, {"Ag": Decimal("30")})
        assert v.melt == Decimal("30.00") and v.melt_missing_spot == ["Pt"]
        it.valuation_rule = "cost"
        assert item_values(db, it, SPOT).current == Decimal("10.00")
        it.valuation_rule = "market"
        assert item_values(db, it, SPOT).current is None  # no market value yet
        assert item_values(db, it, SPOT, market=Decimal("2000")).current == Decimal("2000")
        it.valuation_rule = "max"
        v = item_values(db, it, SPOT, market=Decimal("100"))
        assert v.current == Decimal("1530.00") and v.rule_applied == "melt"
    nometal = create(api, {"item_type": "banknote", "title": "Note"})
    v = values(nometal["id"])
    assert v.melt is None and v.current is None and v.rule_applied == "none"


def test_portfolio_totals(api):
    from app.db import session_factory
    from app.models import Item
    from app.services.valuation import portfolio

    create(api, {"item_type": "coin", "title": "A", "purchase_price": "20", "metal_content": [{"metal": "Ag", "pure_toz": "1"}]})
    create(api, {"item_type": "coin", "title": "B (inherited)", "metal_content": [{"metal": "Ag", "pure_toz": "2"}]})
    create(api, {"item_type": "coin", "title": "C (gift)", "purchase_price": "50", "cost_basis_status": "estimated",
                 "metal_content": [{"metal": "Au", "pure_toz": "0.1"}]})
    with session_factory()() as db:
        items = list(db.scalars(select(Item)))
        p = portfolio(db, items, SPOT, {}, {}, {})
    assert p.melt == Decimal("490.00")  # 30 + 60 + 400
    assert p.cost == Decimal("70.00") and p.cost_estimated == Decimal("50.00")
    assert p.cost_unknown_items == 1 and p.estimated_cost_items == 1
    assert p.gain == Decimal("360.00") and p.gain_items == 2  # (30-20) + (400-50); B has no cost, so excluded
    assert p.pure_toz == {"Ag": Decimal("3"), "Au": Decimal("0.1")}
    assert p.by_metal["Ag"].melt == Decimal("90.00") and p.by_metal["Ag"].current == Decimal("90.00")
