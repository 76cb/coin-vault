"""Goldbacks: the series and denominations to pick from, adding several at once, and how many you hold."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Item
from app.schemas import ItemCreate, _Base
from app.services import goldbacks as gb
from app.services import items as item_svc
from app.services import spot as spot_svc

router = APIRouter(prefix="/goldbacks", tags=["goldbacks"])


class SeriesOut(BaseModel):
    name: str
    first_year: int


class DenominationOut(BaseModel):
    value: Decimal
    label: str
    gold_toz: Decimal
    common: bool


class CatalogueOut(BaseModel):
    series: list[SeriesOut]
    denominations: list[DenominationOut]
    source: str


@router.get("/catalogue", response_model=CatalogueOut)
def catalogue(principal: Principal = Depends(read_items)):
    """The series (by first year) and the denominations, each with its gold."""
    return CatalogueOut(
        series=[SeriesOut(name=n, first_year=y) for n, y in gb.SERIES],
        denominations=[
            DenominationOut(value=d, label=gb.denomination_label(d), gold_toz=gb.gold_toz(d), common=d in gb.COMMON)  # type: ignore[arg-type]
            for d in gb.DENOMINATIONS
        ],
        source=gb.SOURCE,
    )


class AddRow(_Base):
    denomination: Decimal
    quantity: int = Field(ge=1, le=100000)
    price_total: Decimal | None = Field(default=None, ge=0)  # what was paid for all of them

    @field_validator("denomination")
    @classmethod
    def _known(cls, v: Decimal) -> Decimal:
        if Decimal(v) not in gb.DENOMINATIONS:
            raise ValueError("Goldbacks come in 1/4, 1/2, 1, 2, 3, 5, 10, 25, 50 and 100")
        return v


class AddIn(_Base):
    state: str = Field(min_length=1, max_length=60)
    year: int | None = Field(default=None, ge=2019, le=2200)
    variety: str | None = Field(default=None, max_length=120)
    acquired_date: dt.date | None = None
    location_id: int | None = None
    purchase_source: str | None = Field(default=None, max_length=200)
    rows: list[AddRow] = Field(min_length=1, max_length=len(gb.DENOMINATIONS))


class AddOut(BaseModel):
    item_ids: list[int]


@router.post("", response_model=AddOut, status_code=201)
def add(body: AddIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """One item per denomination, each with its count; the gold is worked out from the denomination."""
    if len({r.denomination for r in body.rows}) != len(body.rows):
        raise HTTPException(422, "Each denomination once, please")
    ids = []
    for r in body.rows:
        item = item_svc.create_item(db, principal, ItemCreate(
            item_type="goldback", title=gb.title(body.state, r.denomination, body.year), quantity=r.quantity,
            details={"state": body.state, "denomination": r.denomination, "year": body.year, "variety": body.variety},
            purchase_price=r.price_total, acquired_date=body.acquired_date, location_id=body.location_id,
            purchase_source=body.purchase_source,
        ))
        ids.append(item.id)
    db.commit()
    return AddOut(item_ids=ids)


class SummaryRow(BaseModel):
    state: str | None
    denomination: Decimal | None
    label: str
    notes: int  # how many notes
    goldbacks: Decimal  # their face, in Goldbacks
    gold_toz: Decimal
    melt: Decimal | None
    item_ids: list[int]


class SummaryOut(BaseModel):
    currency: str
    rows: list[SummaryRow]
    notes: int
    goldbacks: Decimal
    gold_toz: Decimal
    melt: Decimal | None


@router.get("/summary", response_model=SummaryOut)
def summary(principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    """How many you hold (not sold), by series and denomination, with their gold at today's spot price."""
    currency = principal.user.base_currency
    gold = spot_svc.spot_map(db, currency).get("Au")
    items = db.scalars(
        select(Item).where(Item.owner_id == principal.owner_id, Item.item_type == "goldback", Item.deleted_at.is_(None),
                           Item.status != "sold").options(selectinload(Item.goldback))
    )
    groups: dict[tuple[str | None, Decimal | None], SummaryRow] = {}
    for it in items:
        g = it.goldback
        state, denom = (g.state if g else None), (g.denomination.normalize() if g and g.denomination is not None else None)
        row = groups.setdefault((state, denom), SummaryRow(
            state=state, denomination=denom, label=gb.denomination_label(denom) if denom is not None else "?",
            notes=0, goldbacks=Decimal(0), gold_toz=Decimal(0), melt=None, item_ids=[],
        ))
        row.notes += it.quantity
        row.item_ids.append(it.id)
        if denom is not None:
            row.goldbacks += denom * it.quantity
            row.gold_toz += (gb.gold_toz(denom) or 0) * it.quantity
    rows = sorted(groups.values(), key=lambda r: (r.state or "~", r.denomination if r.denomination is not None else Decimal(10**6)))
    for r in rows:
        r.melt = (r.gold_toz * gold).quantize(Decimal("0.01")) if gold is not None else None
    total_gold = sum((r.gold_toz for r in rows), Decimal(0))
    return SummaryOut(
        currency=currency, rows=rows, notes=sum(r.notes for r in rows), goldbacks=sum((r.goldbacks for r in rows), Decimal(0)),
        gold_toz=total_gold, melt=(total_gold * gold).quantize(Decimal("0.01")) if gold is not None and rows else None,
    )
