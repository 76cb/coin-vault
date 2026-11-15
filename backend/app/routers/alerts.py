"""Spot price alerts and the want list."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items, require_scope, write_items
from app.models import Item, SpotAlert, WantItem, utcnow
from app.services import alerts as alert_svc
from app.services import spot as spot_svc

router = APIRouter(tags=["alerts"])
read_prices = require_scope("prices:read")


class AlertIn(BaseModel):
    metal: Literal["Au", "Ag", "Pt", "Pd"]
    direction: Literal["above", "below"]
    price: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    note: str | None = Field(default=None, max_length=200)


class AlertOut(BaseModel):
    id: int
    metal: str
    direction: str
    price: Decimal
    currency: str
    note: str | None
    created_at: dt.datetime
    triggered_at: dt.datetime | None
    triggered_price: Decimal | None
    dismissed_at: dt.datetime | None
    spot: Decimal | None  # today's price, for comparison


def _out(a: SpotAlert, spot: dict[str, Decimal]) -> AlertOut:
    return AlertOut(**{k: getattr(a, k) for k in AlertOut.model_fields if k != "spot"}, spot=spot.get(a.metal))


def _mine(db: Session, principal: Principal, alert_id: int) -> SpotAlert:
    a = db.get(SpotAlert, alert_id)
    if a is None or a.owner_id != principal.owner_id:
        raise HTTPException(404, "No such alert")
    return a


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(principal: Principal = Depends(read_prices), db: Session = Depends(get_db)):
    spot = spot_svc.spot_map(db, principal.user.base_currency)
    rows = db.scalars(select(SpotAlert).where(SpotAlert.owner_id == principal.owner_id).order_by(SpotAlert.metal, SpotAlert.price))
    return [_out(a, spot) for a in rows]


@router.post("/alerts", response_model=AlertOut, status_code=201)
def create_alert(body: AlertIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    currency = principal.user.base_currency
    a = SpotAlert(owner_id=principal.owner_id, currency=currency, **body.model_dump())
    db.add(a)
    db.commit()
    spot = spot_svc.spot_map(db, currency)
    alert_svc.check(db, currency, spot)  # a level the price is already past fires straight away
    return _out(a, spot)


@router.post("/alerts/{alert_id}/dismiss", response_model=AlertOut)
def dismiss_alert(alert_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    a = _mine(db, principal, alert_id)
    a.dismissed_at = utcnow()
    db.commit()
    return _out(a, spot_svc.spot_map(db, a.currency))


@router.post("/alerts/{alert_id}/rearm", response_model=AlertOut)
def rearm_alert(alert_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Wait for the level again. If the price is still past it, it fires again at the next price check."""
    a = _mine(db, principal, alert_id)
    a.triggered_at = a.triggered_price = a.dismissed_at = None
    db.commit()
    return _out(a, spot_svc.spot_map(db, a.currency))


@router.delete("/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    db.delete(_mine(db, principal, alert_id))
    db.commit()
    return Response(status_code=204)


# --- Want list ---------------------------------------------------------------------------------


class WantIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    target_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    notes: str | None = Field(default=None, max_length=2000)


class WantPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    target_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    notes: str | None = Field(default=None, max_length=2000)
    found: bool | None = None  # true: got it; false: still looking
    found_item_id: int | None = None


class WantOut(BaseModel):
    id: int
    title: str
    target_price: Decimal | None
    notes: str | None
    created_at: dt.datetime
    found_at: dt.datetime | None
    found_item_id: int | None


def _want(db: Session, principal: Principal, want_id: int) -> WantItem:
    w = db.get(WantItem, want_id)
    if w is None or w.owner_id != principal.owner_id:
        raise HTTPException(404, "Not on the want list")
    return w


@router.get("/wants", response_model=list[WantOut])
def list_wants(principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    rows = db.scalars(select(WantItem).where(WantItem.owner_id == principal.owner_id)
                      .order_by(WantItem.found_at.is_not(None), WantItem.created_at.desc(), WantItem.id.desc()))
    return [WantOut.model_validate(w, from_attributes=True) for w in rows]


@router.post("/wants", response_model=WantOut, status_code=201)
def create_want(body: WantIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    w = WantItem(owner_id=principal.owner_id, **body.model_dump())
    db.add(w)
    db.commit()
    return WantOut.model_validate(w, from_attributes=True)


@router.patch("/wants/{want_id}", response_model=WantOut)
def update_want(want_id: int, body: WantPatch, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    w = _want(db, principal, want_id)
    data = body.model_dump(exclude_unset=True)
    for k in ("title", "target_price", "notes"):
        if k in data and (k != "title" or data[k]):
            setattr(w, k, data[k])
    if data.get("found_item_id") is not None:
        item = db.get(Item, data["found_item_id"])
        if item is None or item.owner_id != principal.owner_id:
            raise HTTPException(422, "Unknown item")
        w.found_item_id, w.found_at = item.id, w.found_at or utcnow()
    if "found" in data and data["found"] is not None:
        w.found_at = (w.found_at or utcnow()) if data["found"] else None
        if not data["found"]:
            w.found_item_id = None
    db.commit()
    return WantOut.model_validate(w, from_attributes=True)


@router.delete("/wants/{want_id}", status_code=204)
def delete_want(want_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    db.delete(_want(db, principal, want_id))
    db.commit()
    return Response(status_code=204)
