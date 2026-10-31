"""Export the collection: a CSV of every field, and the insurance report's data (the page itself prints it)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items
from app.models import Item, Location, utcnow
from app.routers.items import ITEM_LOAD, SORTS, ItemFilters, filtered_items, item_filters
from app.services import exports
from app.services import items as item_svc
from app.services import spot as spot_svc

router = APIRouter(tags=["exports"])

METAL_LABELS = {"Au": "Gold", "Ag": "Silver", "Pt": "Platinum", "Pd": "Palladium"}


def _paths(db: Session, owner_id: int) -> dict[int, str | None]:
    return {loc.id: item_svc.location_path(db, loc.id) for loc in db.scalars(select(Location).where(Location.owner_id == owner_id))}


def _today() -> dt.date:
    from app.config import get_settings

    return utcnow().astimezone(ZoneInfo(get_settings().timezone)).date()


@router.get("/export/items.csv")
def export_csv(
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
    f: ItemFilters = Depends(item_filters),
    sort: Literal["updated", "created", "title", "acquired", "year"] = "title",
):
    """Every item matching the Collection page's filters, one row each, with its values today."""
    items = db.scalars(filtered_items(principal.owner_id, f).order_by(SORTS[sort], Item.id).options(*ITEM_LOAD)).unique().all()
    currency = principal.user.base_currency
    spot = spot_svc.spot_map(db, currency)
    paths = _paths(db, principal.owner_id)
    rows = (exports.csv_row(db, it, paths, spot, currency) for it in items)
    return StreamingResponse(
        exports.csv_stream(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="coinvault-items-{_today()}.csv"', "Cache-Control": "no-store"},
    )


class SpotUsed(BaseModel):
    metal: str
    label: str
    price: Decimal
    price_time: dt.datetime | None


class ReportItemOut(BaseModel):
    id: int
    title: str
    kind: str
    status: str
    quantity: int
    description: str
    grade: str | None
    identifiers: list[str]
    metals: str
    location: str | None
    acquired_date: dt.date | None
    cost: Decimal | None
    current: Decimal | None
    current_each: Decimal | None
    basis: str
    photos: list[str]


class ReportGroupOut(BaseModel):
    label: str
    count: int
    pieces: int
    current: Decimal


class ReportOut(BaseModel):
    owner: str
    date: dt.date
    generated_at: dt.datetime
    currency: str
    spot: list[SpotUsed]
    count: int
    pieces: int
    current: Decimal
    melt: Decimal
    cost: Decimal
    cost_items: int
    unvalued: int
    by_location: list[ReportGroupOut]
    items: list[ReportItemOut]


ORDERS = {"value": None, "title": (Item.title.asc(),), "location": None, "acquired": (Item.acquired_date.asc(),)}


@router.get("/report", response_model=ReportOut)
def insurance_report(
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
    f: ItemFilters = Depends(item_filters),
    order: Literal["value", "title", "location", "acquired"] = "value",
):
    """What you hold today (not sold, not deleted) with descriptions, identifying numbers, photos and values."""
    stmt = filtered_items(principal.owner_id, ItemFilters(**{**vars(f), "deleted": False})).where(Item.status != "sold")
    items = list(db.scalars(stmt.order_by(Item.title, Item.id).options(*ITEM_LOAD)).unique().all())
    if order == "acquired":
        items.sort(key=lambda it: (it.acquired_date is None, it.acquired_date or dt.date.max, it.title.lower()))
    currency = principal.user.base_currency
    spot_latest = spot_svc.latest(db, currency)
    spot = {m: l.price.price_per_toz for m, l in spot_latest.items() if l.price is not None}
    paths = _paths(db, principal.owner_id)
    r = exports.report(db, items, paths, spot, currency)
    if order == "value":
        r.items.sort(key=lambda i: (i.current is None, -(i.current or 0), i.title.lower()))
    elif order == "location":
        r.items.sort(key=lambda i: (i.location is None, (i.location or "").lower(), i.title.lower()))
    held = {m for it in items for m in exports.valuation.pure_per_unit(db, it)}
    return ReportOut(
        owner=principal.user.username, date=_today(), generated_at=utcnow(), currency=currency,
        spot=[SpotUsed(metal=m, label=METAL_LABELS[m], price=l.price.price_per_toz, price_time=l.price_time)
              for m, l in spot_latest.items() if l.price is not None and m in held],
        count=r.count, pieces=r.pieces, current=r.current, melt=r.melt, cost=r.cost, cost_items=r.cost_items, unvalued=r.unvalued,
        by_location=[ReportGroupOut(**vars(g)) for g in r.by_location],
        items=[ReportItemOut(**vars(i)) for i in r.items],
    )
