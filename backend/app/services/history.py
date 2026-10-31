"""What the collection was worth on each past day.

For each day: the items held that day (from the acquired date, or the day they were added when there's no
acquired date, until the sale date), each valued the way the dashboard values it today, but with that day's
closing spot price and the market values known by then. Today's point uses the latest spot price, so it
matches the dashboard.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Item, SpotPrice, Valuation, utcnow
from app.services import valuation as val

ZERO = Decimal(0)


@dataclass
class Point:
    day: dt.date
    value: Decimal
    paid: Decimal
    items: int
    pieces: int
    unvalued: int  # held that day but with no value (no spot price yet, no market value)


@dataclass
class Change:
    count: int = 0
    amount: Decimal = ZERO


@dataclass
class History:
    currency: str
    start: dt.date | None
    end: dt.date
    step_days: int
    points: list[Point]
    first_spot: dt.date | None  # spot prices have been recorded since this day
    clipped: bool  # the range was cut short because there were no spot prices before first_spot
    undated: int  # items counted from the day they were added, having no acquired date
    no_cost: int  # items held at the end with no purchase price (not in the paid line)
    added: Change = field(default_factory=Change)  # bought in the range: count and what was paid
    sold: Change = field(default_factory=Change)  # sold in the range: count and sale proceeds


@dataclass
class _Held:
    item: Item
    start: dt.date
    end: dt.date | None  # first day no longer held
    per_unit: dict[str, Decimal]
    qty: Decimal
    cost: Decimal | None
    values: list[Valuation]  # in this currency, newest first
    slabbed: bool

    def held_on(self, d: dt.date) -> bool:
        return self.start <= d and (self.end is None or d < self.end)


def _utc(t: dt.datetime) -> dt.datetime:
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def _local_day(t: dt.datetime, tz: ZoneInfo) -> dt.date:
    return _utc(t).astimezone(tz).date()


def _items(db: Session, owner_id: int) -> list[Item]:
    return list(
        db.scalars(
            select(Item)
            .where(Item.owner_id == owner_id, Item.deleted_at.is_(None))
            .options(selectinload(Item.metal_content), selectinload(Item.lot), selectinload(Item.valuations),
                     selectinload(Item.condition))
        )
    )


def _spot_by_day(db: Session, currency: str, metals: set[str], days: list[dt.date], tz: ZoneInfo, today: dt.date):
    """For each metal, the last price on or before the end of each day (today: the latest price)."""
    out: dict[str, list[Decimal | None]] = {}
    if not days:
        return out
    begin = dt.datetime.combine(days[0], dt.time(), tz).astimezone(dt.UTC)
    for metal in metals:
        base = (SpotPrice.metal == metal, SpotPrice.currency == currency)
        before = db.execute(
            select(SpotPrice.price_per_toz).where(*base, SpotPrice.fetched_at < begin)
            .order_by(SpotPrice.fetched_at.desc(), SpotPrice.id.desc()).limit(1)
        ).scalar()
        rows = db.execute(
            select(SpotPrice.fetched_at, SpotPrice.price_per_toz).where(*base, SpotPrice.fetched_at >= begin)
            .order_by(SpotPrice.fetched_at, SpotPrice.id)
        ).all()
        prices: list[Decimal | None] = []
        price, i = before, 0
        for d in days:
            if d >= today:
                price = rows[-1][1] if rows else price
                i = len(rows)
            else:
                cutoff = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(), tz).astimezone(dt.UTC)
                while i < len(rows) and _utc(rows[i][0]) < cutoff:
                    price = rows[i][1]
                    i += 1
            prices.append(price)
        out[metal] = prices
    return out


def _first_spot(db: Session, currency: str, metals: set[str], tz: ZoneInfo) -> dt.date | None:
    """The first day with a price for every metal held (melt values are only complete from then)."""
    firsts = []
    for metal in metals:
        t = db.scalar(select(SpotPrice.fetched_at).where(SpotPrice.metal == metal, SpotPrice.currency == currency)
                      .order_by(SpotPrice.fetched_at).limit(1))
        if t is None:
            return None
        firsts.append(_local_day(t, tz))
    return max(firsts) if firsts else None


def collection_history(
    db: Session,
    owner_id: int,
    currency: str,
    timezone: str,
    days: int | None,
    item_type: str | None = None,
    metal: str | None = None,
    now: dt.datetime | None = None,
) -> History:
    """`days`: how far back (None: since the first item). Long ranges use one point a week."""
    tz = ZoneInfo(timezone)
    today = _local_day(now or utcnow(), tz)
    held: list[_Held] = []
    undated = 0
    for it in _items(db, owner_id):
        if item_type and it.item_type != item_type:
            continue
        per_unit = val.pure_per_unit(db, it)
        if metal and metal not in per_unit:
            continue
        start = it.acquired_date or _local_day(it.created_at, tz)
        start = min(start, today)
        if it.acquired_date is None:
            undated += 1
        end = None
        if it.status == "sold":
            end = it.sale_date or _local_day(it.updated_at, tz)
        held.append(_Held(it, start, end, per_unit, Decimal(it.quantity), val.item_cost(it),
                          [v for v in it.valuations if v.currency == currency], val.is_slabbed(it)))

    metals = {m for h in held for m in h.per_unit}
    first_spot = _first_spot(db, currency, metals, tz) if metals else None
    earliest = min((h.start for h in held), default=today)
    start = earliest if days is None else max(today - dt.timedelta(days=days), earliest)
    clipped = False
    if metals:
        floor = first_spot or today  # no spot price at all: only today can be valued (and only partly)
        if start < floor:
            start, clipped = floor, True
    step = 7 if (today - start).days > 400 else 1
    day_list = []
    d = today
    while d >= start:
        day_list.append(d)
        d -= dt.timedelta(days=step)
    day_list.reverse()

    spot = _spot_by_day(db, currency, metals, day_list, tz, today)
    points = []
    for i, d in enumerate(day_list):
        spot_d = {m: prices[i] for m, prices in spot.items() if prices[i] is not None}
        value = paid = ZERO
        items = pieces = unvalued = 0
        for h in held:
            if not h.held_on(d):
                continue
            items += 1
            pieces += int(h.qty)
            known = [v for v in h.values if v.as_of <= d]
            chosen = val.choose_valuation(known, h.slabbed)
            market = val.money(chosen.value_each * h.qty) if chosen is not None else None
            melt = None
            if h.per_unit and all(m in spot_d for m in h.per_unit):
                melt = val.money(sum((oz * h.qty * spot_d[m] for m, oz in h.per_unit.items()), ZERO))
            current, _ = val.apply_rule(h.item.valuation_rule, melt, market, h.cost)
            if current is None:
                unvalued += 1
            else:
                value += current
            if h.cost is not None:
                paid += h.cost
        points.append(Point(d, val.money(value), val.money(paid), items, pieces, unvalued))

    first = day_list[0] if day_list else today
    out = History(currency=currency, start=day_list[0] if day_list else None, end=today, step_days=step, points=points,
                  first_spot=first_spot, clipped=clipped, undated=undated,
                  no_cost=sum(1 for h in held if h.held_on(today) and h.cost is None))
    for h in held:
        if first < h.start <= today:
            out.added.count += 1
            out.added.amount += h.cost or ZERO
        if h.end is not None and first < h.end <= today:
            out.sold.count += 1
            out.sold.amount += val.money((h.item.sale_price or ZERO) - (h.item.sale_fees or ZERO))
    return out

