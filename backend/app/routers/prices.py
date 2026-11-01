"""Spot prices and portfolio totals."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import scheduler
from app.db import get_db
from app.deps import Principal, require_scope, write_items
from app.models import Item, Location, utcnow
from app.schemas import ITEM_TYPES
from app.services import items as item_svc
from app.services import spot as spot_svc
from app.services import valuation

router = APIRouter(tags=["prices"])
read_prices = require_scope("prices:read")

METAL_LABELS = {"Au": "Gold", "Ag": "Silver", "Pt": "Platinum", "Pd": "Palladium"}
TYPE_LABELS = {
    "coin": "Coins",
    "bullion": "Bullion coins and rounds",
    "bar": "Bars",
    "banknote": "Banknotes",
    "goldback": "Goldbacks",
    "lot": "Junk silver lots",
    "other": "Other",
}
assert set(TYPE_LABELS) == set(ITEM_TYPES)


class SpotOut(BaseModel):
    metal: str
    label: str
    price: Decimal | None
    source: str | None
    fetched_at: dt.datetime | None
    source_timestamp: dt.datetime | None
    price_time: dt.datetime | None  # when the market set this price (source timestamp, else fetch time)
    stale: bool


class SpotLatestOut(BaseModel):
    currency: str
    market_open: bool
    stale_after_minutes: int
    next_poll: dt.datetime | None
    metals: list[SpotOut]


def _latest(db: Session, currency: str) -> SpotLatestOut:
    from app.services.providers import get_system

    data = spot_svc.latest(db, currency)
    return SpotLatestOut(
        currency=currency,
        market_open=spot_svc.market_open(),
        stale_after_minutes=int(get_system(db, "spot_stale_minutes") or 30),
        next_poll=scheduler.next_spot_run(),
        metals=[
            SpotOut(
                metal=m,
                label=METAL_LABELS[m],
                price=l.price.price_per_toz if l.price else None,
                source=l.price.source if l.price else None,
                fetched_at=l.price.fetched_at if l.price else None,
                source_timestamp=l.price.source_timestamp if l.price else None,
                price_time=l.price_time,
                stale=l.stale,
            )
            for m, l in data.items()
        ],
    )


@router.get("/prices/spot/latest", response_model=SpotLatestOut)
def spot_latest(principal: Principal = Depends(read_prices), db: Session = Depends(get_db)):
    return _latest(db, principal.user.base_currency)


class RefreshOut(BaseModel):
    ok: bool
    source: str | None
    old_metals: list[str]
    errors: list[str]
    latest: SpotLatestOut


@router.post("/prices/spot/refresh", response_model=RefreshOut)
def spot_refresh(principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    currency = principal.user.base_currency
    [outcome] = spot_svc.poll(db, [currency], force=True)
    return RefreshOut(ok=outcome.ok, source=outcome.source, old_metals=outcome.old_metals, errors=outcome.errors, latest=_latest(db, currency))


class PricePoint(BaseModel):
    t: dt.datetime
    price: Decimal


class HistoryOut(BaseModel):
    metal: str
    currency: str
    interval: str
    holdings_toz: Decimal
    points: list[PricePoint]


def _bucket(points, interval: str) -> list[PricePoint]:
    """Keep the last price in each hour or day."""
    if interval == "raw":
        return [PricePoint(t=p.fetched_at, price=p.price_per_toz) for p in points]
    out: dict[str, PricePoint] = {}
    for p in points:
        t = p.fetched_at if p.fetched_at.tzinfo else p.fetched_at.replace(tzinfo=dt.UTC)
        key = t.strftime("%Y-%m-%d") if interval == "day" else t.strftime("%Y-%m-%dT%H")
        out[key] = PricePoint(t=t, price=p.price_per_toz)
    return list(out.values())


@router.get("/prices/spot/history", response_model=HistoryOut)
def spot_history(
    metal: Literal["Au", "Ag", "Pt", "Pd"] = "Ag",
    days: int = Query(default=30, ge=1, le=3650),
    principal: Principal = Depends(read_prices),
    db: Session = Depends(get_db),
):
    currency = principal.user.base_currency
    rows = spot_svc.history(db, metal, currency, utcnow() - dt.timedelta(days=days))
    interval = "raw" if days <= 2 else "hour" if days <= 31 else "day"
    items = _owned_items(db, principal)
    holdings = sum((valuation.item_values(db, it, {}).pure_toz_total.get(metal, Decimal(0)) for it in items), Decimal(0))
    return HistoryOut(metal=metal, currency=currency, interval=interval, holdings_toz=holdings, points=_bucket(rows, interval))


def _owned_items(db: Session, principal: Principal) -> list[Item]:
    return list(
        db.scalars(
            select(Item)
            .where(Item.owner_id == principal.owner_id, Item.deleted_at.is_(None), Item.status != "sold")
            .options(selectinload(Item.metal_content), selectinload(Item.lot), selectinload(Item.valuations))
        )
    )


class BucketOut(BaseModel):
    key: str
    label: str
    count: int
    pieces: int
    pure_toz: Decimal
    melt: Decimal
    cost: Decimal
    current: Decimal


class TotalsOut(BaseModel):
    item_count: int
    pieces: int
    melt: Decimal
    market: Decimal
    market_items: int
    valued_at_market: int
    cost: Decimal
    cost_estimated: Decimal
    current: Decimal
    gain: Decimal
    gain_items: int
    cost_unknown_items: int
    estimated_cost_items: int
    no_value_items: int


class SummaryOut(BaseModel):
    currency: str
    spot: SpotLatestOut
    totals: TotalsOut
    pure_toz: dict[str, Decimal]
    by_metal: list[BucketOut]
    by_type: list[BucketOut]
    by_location: list[BucketOut]
    market_values_available: bool


@router.get("/portfolio/summary", response_model=SummaryOut)
def portfolio_summary(principal: Principal = Depends(read_prices), db: Session = Depends(get_db)):
    currency = principal.user.base_currency
    spot = spot_svc.spot_map(db, currency)
    paths = {
        loc.id: item_svc.location_path(db, loc.id) or loc.name
        for loc in db.scalars(select(Location).where(Location.owner_id == principal.owner_id))
    }
    p = valuation.portfolio(db, _owned_items(db, principal), spot, paths, TYPE_LABELS, METAL_LABELS, currency)

    def buckets(d) -> list[BucketOut]:
        out = [BucketOut(**{k: getattr(b, k) for k in BucketOut.model_fields}) for b in d.values()]
        return sorted(out, key=lambda b: (-(b.current or b.melt), b.label))

    q = valuation.money
    return SummaryOut(
        currency=currency,
        spot=_latest(db, currency),
        totals=TotalsOut(
            item_count=p.item_count,
            pieces=p.pieces,
            melt=q(p.melt),
            market=q(p.market),
            market_items=p.market_items,
            valued_at_market=p.valued_at_market,
            cost=q(p.cost),
            cost_estimated=q(p.cost_estimated),
            current=q(p.current),
            gain=q(p.gain),
            gain_items=p.gain_items,
            cost_unknown_items=p.cost_unknown_items,
            estimated_cost_items=p.estimated_cost_items,
            no_value_items=p.no_value_items,
        ),
        pure_toz=p.pure_toz,
        by_metal=buckets(p.by_metal),
        by_type=buckets(p.by_type),
        by_location=buckets(p.by_location),
        market_values_available=True,
    )


class ValuePoint(BaseModel):
    day: dt.date
    value: Decimal
    paid: Decimal
    items: int
    pieces: int
    unvalued: int


class ChangeOut(BaseModel):
    count: int
    amount: Decimal


class ValueHistoryOut(BaseModel):
    currency: str
    start: dt.date | None
    end: dt.date
    step_days: int
    first_spot: dt.date | None
    clipped: bool
    undated: int
    no_cost: int
    added: ChangeOut
    sold: ChangeOut
    points: list[ValuePoint]


@router.get("/portfolio/history", response_model=ValueHistoryOut)
def portfolio_history(
    days: int = Query(default=90, ge=0, le=3650, description="how far back; 0 for everything"),
    item_type: str | None = Query(default=None, alias="type"),
    metal: Literal["Au", "Ag", "Pt", "Pd"] | None = None,
    principal: Principal = Depends(read_prices),
    db: Session = Depends(get_db),
):
    """What the collection was worth on each day: what you held then, at that day's spot price and the market values known then."""
    from app.config import get_settings
    from app.services.history import collection_history

    if item_type is not None and item_type not in TYPE_LABELS:
        raise HTTPException(422, f"Unknown type {item_type!r}")
    h = collection_history(db, principal.owner_id, principal.user.base_currency, get_settings().timezone,
                           days or None, item_type=item_type, metal=metal)
    return ValueHistoryOut(
        currency=h.currency, start=h.start, end=h.end, step_days=h.step_days, first_spot=h.first_spot, clipped=h.clipped,
        undated=h.undated, no_cost=h.no_cost, added=ChangeOut(**vars(h.added)), sold=ChangeOut(**vars(h.sold)),
        points=[ValuePoint(**vars(p)) for p in h.points],
    )
