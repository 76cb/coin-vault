"""POST /items/describe: turn a listing title into a filled-in (unsaved) item."""

from __future__ import annotations

import re
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items
from app.models import Composition
from app.routers.compositions import CompositionMatchOut, _out, _visible, match
from app.services.describe import describe

router = APIRouter(tags=["items"])

UNIT_G = {"g": Decimal(1), "ozt": Decimal("31.1034768"), "kg": Decimal(1000), "tola": Decimal("11.6638038")}


class DescribeIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class DescribeOut(BaseModel):
    item_type: str
    title: str
    quantity: int
    metal: str | None
    details: dict
    condition: dict | None
    recognized: list[str]
    notes: list[str]
    compositions: list[CompositionMatchOut]  # best first; equal scores fit equally well


PRODUCT_WORDS = ("combibar", "fortuna", "skyline", "multidisc", "kinebar")


def _bar_matches(db: Session, principal: Principal, metal: str | None, refiner: str | None, weight: str | None, unit: str | None, text: str = ""):
    if not metal or not weight:
        return []
    try:
        grams = Decimal(weight) * UNIT_G[unit or "g"]
    except Exception:
        return []
    out = []
    for c in db.scalars(select(Composition).where(_visible(principal), Composition.denomination == "bar", Composition.metal == metal)):
        if c.gross_weight_g is None or abs(c.gross_weight_g - grams) > grams * Decimal("0.005"):
            continue
        score = 5
        if refiner:
            if not c.label.lower().startswith(refiner.lower().split()[0]):
                continue
            score += 5
        # a named product line ("CombiBar") beats the plain bar of the same weight
        low = text.lower()
        score += sum(3 for w in PRODUCT_WORDS if w in low and w in c.label.lower())
        if any(w in c.label.lower() for w in PRODUCT_WORDS) and not any(w in low for w in PRODUCT_WORDS):
            score -= 1
        pieces = re.search(r"\b(\d{1,3})\s?x\s?(\d+(?:\.\d+)?)\s?(g|gram|grams|oz)\b", low)
        if pieces:
            unit = "oz" if pieces.group(3) == "oz" else "g"
            if f"{pieces.group(1)} x {pieces.group(2)} {unit}" in c.label.lower():
                score += 2
        out.append((score, c))
    out.sort(key=lambda sc: (-sc[0], sc[1].label))
    return [CompositionMatchOut(**_out(c).model_dump(), score=s) for s, c in out[:5]]


@router.post("/items/describe", response_model=DescribeOut)
def describe_item(body: DescribeIn, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    d = describe(body.text)
    comps: list[CompositionMatchOut] = []
    if d.composition_key:
        c = db.scalar(select(Composition).where(_visible(principal), Composition.key == d.composition_key))
        if c is not None:
            comps = [CompositionMatchOut(**_out(c).model_dump(), score=100)]
    elif d.item_type == "bar":
        comps = _bar_matches(db, principal, d.metal, d.details.get("refiner"), d.details.get("weight_value"), d.details.get("weight_unit"), d.title)
    elif d.item_type == "coin" and (d.details.get("denomination") or d.details.get("series")):
        comps = match(
            country=d.details.get("country"), denomination=d.details.get("denomination"), year=d.details.get("year"),
            mint_mark=d.details.get("mint_mark"), series=d.title, principal=principal, db=db,
        )
    return DescribeOut(
        item_type=d.item_type, title=d.title, quantity=d.quantity, metal=d.metal, details=d.details,
        condition=d.condition, recognized=d.recognized, notes=d.notes, compositions=comps,
    )
