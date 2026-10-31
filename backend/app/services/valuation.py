"""Melt value, current value and portfolio totals.

Melt per item = quantity x sum over metals (pure troy oz per piece x spot per troy oz).
Junk lots with a per-face composition: pure oz = face value x pure oz per $1 face.
Current value follows the item's rule: max(melt, market) by default; market values arrive in Milestone 3.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models import Valuation, Composition, Item

CENT = Decimal("0.01")
ZERO = Decimal(0)


def money(v: Decimal | None) -> Decimal | None:
    return None if v is None else v.quantize(CENT, rounding=ROUND_HALF_UP)


def pure_per_unit(db: Session, item: Item) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for m in item.metal_content:
        if m.pure_toz is not None:
            out[m.metal] += m.pure_toz
    if not out and item.item_type == "lot" and item.lot and item.lot.face_value and item.lot.composition_id:
        comp = db.get(Composition, item.lot.composition_id)
        if comp is not None and comp.per_face_unit:
            out[comp.metal] += item.lot.face_value * comp.pure_toz
    return dict(out)


@dataclass
class ItemValues:
    pure_toz_per_unit: dict[str, Decimal]
    pure_toz_total: dict[str, Decimal]
    melt_by_metal: dict[str, Decimal]
    melt: Decimal | None  # None when the item has no metal content
    melt_missing_spot: list[str]
    market: Decimal | None
    market_valuation: "Valuation | None"
    cost: Decimal | None
    current: Decimal | None
    rule: str
    rule_applied: str  # what current value actually used: melt, market, cost or none

    @property
    def gain(self) -> Decimal | None:
        if self.current is None or self.cost is None:
            return None
        return self.current - self.cost


_AUTO = object()


def is_raw_estimate(v: Valuation) -> bool:
    """A catalogue estimate for raw coins (Numista's G to Unc bands), not a price for a graded, slabbed coin."""
    return bool(v.details and "numista" in v.details)


def latest_valuation(item: Item, currency: str | None) -> Valuation | None:
    """The market value in use, in this currency (a value in another currency is ignored, not converted).

    The one the owner chose, if any; else the newest. For a slabbed coin a raw-coin catalogue estimate (Numista)
    only counts when there's nothing else: sold listings, a price guide or the owner's own figure come first.
    """
    values = [v for v in item.valuations if currency is None or v.currency == currency]  # newest first
    return choose_valuation(values, is_slabbed(item))


def is_slabbed(item: Item) -> bool:
    return item.condition is not None and item.condition.grading == "slabbed"


def choose_valuation(values: list[Valuation], slabbed: bool) -> Valuation | None:
    """From values newest first: the pinned one, else (slabbed) the newest that isn't a raw estimate, else the newest."""
    chosen = next((v for v in values if v.pinned), None)
    if chosen is not None:
        return chosen
    if slabbed:
        graded = next((v for v in values if not is_raw_estimate(v)), None)
        if graded is not None:
            return graded
    return values[0] if values else None


def apply_rule(rule: str, melt: Decimal | None, market: Decimal | None, cost: Decimal | None) -> tuple[Decimal | None, str]:
    """The item's current value under its valuation rule, and which figure that was (melt, market, cost or none)."""
    if rule == "melt":
        return melt, "melt" if melt is not None else "none"
    if rule == "market":
        return market, "market" if market is not None else "none"
    if rule == "cost":
        return cost, "cost" if cost is not None else "none"
    candidates = [(v, n) for v, n in ((melt, "melt"), (market, "market")) if v is not None]  # max
    return max(candidates, key=lambda c: c[0]) if candidates else (None, "none")


def item_cost(item: Item) -> Decimal | None:
    return None if item.purchase_price is None else money(item.purchase_price + (item.purchase_fees or ZERO))


def item_values(
    db: Session, item: Item, spot: dict[str, Decimal], market=_AUTO, currency: str | None = None
) -> ItemValues:
    """`market` is the whole item's market value; by default it comes from the item's newest valuation."""
    valuation = None
    if market is _AUTO:
        valuation = latest_valuation(item, currency)
        market = money(valuation.value_each * item.quantity) if valuation is not None else None
    per_unit = pure_per_unit(db, item)
    qty = Decimal(item.quantity)
    total = {m: v * qty for m, v in per_unit.items()}
    by_metal: dict[str, Decimal] = {}
    missing: list[str] = []
    for metal, oz in total.items():
        price = spot.get(metal)
        if price is None:
            missing.append(metal)
        else:
            by_metal[metal] = money(oz * price)
    melt = money(sum(by_metal.values(), ZERO)) if by_metal else None
    cost = item_cost(item)
    rule = item.valuation_rule
    current, applied = apply_rule(rule, melt, market, cost)
    return ItemValues(
        pure_toz_per_unit=per_unit,
        pure_toz_total=total,
        melt_by_metal=by_metal,
        melt=melt,
        melt_missing_spot=missing,
        market=market,
        market_valuation=valuation,
        cost=cost,
        current=current,
        rule=rule,
        rule_applied=applied,
    )


@dataclass
class Bucket:
    key: str
    label: str
    count: int = 0
    pieces: int = 0
    pure_toz: Decimal = ZERO
    melt: Decimal = ZERO
    cost: Decimal = ZERO
    current: Decimal = ZERO


@dataclass
class Portfolio:
    item_count: int = 0
    pieces: int = 0
    melt: Decimal = ZERO
    market: Decimal = ZERO
    market_items: int = 0  # items with a market value
    valued_at_market: int = 0  # items whose current value is their market value
    cost: Decimal = ZERO
    cost_estimated: Decimal = ZERO
    current: Decimal = ZERO
    gain: Decimal = ZERO
    gain_items: int = 0
    cost_unknown_items: int = 0
    no_value_items: int = 0
    estimated_cost_items: int = 0
    pure_toz: dict[str, Decimal] = field(default_factory=dict)
    by_metal: dict[str, Bucket] = field(default_factory=dict)
    by_type: dict[str, Bucket] = field(default_factory=dict)
    by_location: dict[str, Bucket] = field(default_factory=dict)


def portfolio(
    db: Session,
    items: list[Item],
    spot: dict[str, Decimal],
    location_paths: dict[int, str],
    type_labels: dict[str, str],
    metal_labels: dict[str, str],
    currency: str | None = None,
) -> Portfolio:
    p = Portfolio()
    pure: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for item in items:
        v = item_values(db, item, spot, currency=currency)
        p.item_count += 1
        if v.market is not None:
            p.market += v.market
            p.market_items += 1
        if v.rule_applied == "market":
            p.valued_at_market += 1
        p.pieces += item.quantity
        p.melt += v.melt or ZERO
        if v.cost is not None:
            p.cost += v.cost
            if item.cost_basis_status == "estimated":
                p.cost_estimated += v.cost
                p.estimated_cost_items += 1
        else:
            p.cost_unknown_items += 1
        if v.current is None:
            p.no_value_items += 1
        else:
            p.current += v.current
        if v.gain is not None:
            p.gain += v.gain
            p.gain_items += 1
        for metal, oz in v.pure_toz_total.items():
            pure[metal] += oz
            b = p.by_metal.setdefault(metal, Bucket(metal, metal_labels.get(metal, metal)))
            b.count += 1
            b.pieces += item.quantity
            b.pure_toz += oz
            b.melt += v.melt_by_metal.get(metal, ZERO)
            b.current += v.melt_by_metal.get(metal, ZERO)  # by metal, value means metal value
        tb = p.by_type.setdefault(item.item_type, Bucket(item.item_type, type_labels.get(item.item_type, item.item_type)))
        loc_key = str(item.location_id) if item.location_id else "none"
        lb = p.by_location.setdefault(
            loc_key, Bucket(loc_key, location_paths.get(item.location_id, "No location") if item.location_id else "No location")
        )
        for b in (tb, lb):
            b.count += 1
            b.pieces += item.quantity
            b.melt += v.melt or ZERO
            b.cost += v.cost or ZERO
            b.current += v.current or ZERO
    p.pure_toz = dict(pure)
    return p
