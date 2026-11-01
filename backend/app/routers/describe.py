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
from app.services import base_metals
from app.services.coin_words import denom_key
from app.services.describe import LINE_WORDS, Described, describe

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


def _bullion_matches(db: Session, principal: Principal, line: str, country: str | None, metal: str | None,
                     size_toz: Decimal | None, year: int | None, denomination: str | None = None) -> list[CompositionMatchOut]:
    """Reference rows of a bullion line in the size the text gives; with no size, the one with the face value it
    gives ("$15"); with neither, 1 oz."""
    base = re.sub(r"^(Gold|Silver|Platinum|Palladium)\s+", "", line)
    word = LINE_WORDS.get(base, base.split()[-1].lower())
    by_face = denom_key(denomination) if size_toz is None and denomination else None
    target = size_toz or Decimal(1)
    scored: list[tuple[int, Composition]] = []
    stmt = select(Composition).where(_visible(principal), Composition.per_face_unit.is_(False), Composition.label.ilike(f"%{word}%"))
    if metal:
        stmt = stmt.where(Composition.metal == metal)
    for c in db.scalars(stmt):
        if by_face:
            if denom_key(c.denomination) != by_face:
                continue
        elif abs(c.pure_toz - target) > target * Decimal("0.02"):
            continue
        score = 5
        if country and c.country == country:
            score += 2
        if year is not None and (c.year_from or c.year_to):
            if (c.year_from and year < c.year_from) or (c.year_to and year > c.year_to):
                continue
            score += 3
        scored.append((score, c))
    scored.sort(key=lambda sc: (-sc[0], sc[1].label))
    return [CompositionMatchOut(**_out(c).model_dump(), score=sc) for sc, c in scored[:5]]


@router.post("/items/describe", response_model=DescribeOut)
def describe_item(body: DescribeIn, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    return described_out(db, principal, describe(body.text))


def described_out(db: Session, principal: Principal, d: Described) -> DescribeOut:
    """What the title reader understood, with the reference compositions that fit it."""
    comps: list[CompositionMatchOut] = []
    face = d.details.get("denomination") if d.item_type == "bullion" and d.size_toz is None else None
    if d.composition_key:
        c = db.scalar(select(Composition).where(_visible(principal), Composition.key == d.composition_key))
        # the 1 oz row a bullion line defaults to, unless the title's face value says another size ("Kangaroo $15")
        if c is not None and face and d.details.get("product_line") and denom_key(c.denomination) != denom_key(face):
            comps = _bullion_matches(db, principal, d.details["product_line"], d.details.get("country"), d.metal, None,
                                     d.details.get("year"), face)
        if c is not None and not comps:
            comps = [CompositionMatchOut(**_out(c).model_dump(), score=100)]
    elif d.item_type == "bar":
        comps = _bar_matches(db, principal, d.metal, d.details.get("refiner"), d.details.get("weight_value"), d.details.get("weight_unit"), d.title)
    elif d.item_type == "bullion" and d.details.get("product_line"):
        comps = _bullion_matches(db, principal, d.details["product_line"], d.details.get("country"), d.metal, d.size_toz,
                                 d.details.get("year"), d.details.get("denomination"))
    elif d.item_type == "coin" and (d.details.get("denomination") or d.details.get("series")):
        comps = match(
            country=d.details.get("country"), denomination=d.details.get("denomination"), year=d.details.get("year"),
            mint_mark=d.details.get("mint_mark"), series=d.title, principal=principal, db=db,
        )
    if d.item_type == "coin" and not comps and d.metal is None:
        hit = base_metals.lookup(d.details.get("country"), d.details.get("denomination"), d.details.get("year"),
                                 d.details.get("mint_mark"), d.details.get("series"))
        if hit is not None:
            d.details["composition"] = hit.composition
            if hit.weight_g is not None:
                d.details["weight_g"] = str(hit.weight_g)
            d.recognized.append("no precious metal")
    return DescribeOut(
        item_type=d.item_type, title=d.title, quantity=d.quantity, metal=d.metal, details=d.details,
        condition=d.condition, recognized=d.recognized, notes=d.notes, compositions=comps,
    )
