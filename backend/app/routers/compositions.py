"""Reference table of standard compositions (actual silver/gold weight)."""

from __future__ import annotations

import re
import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.compositions_seed import SILVER_ONLY_PREFIXES
from app.models import Composition, ItemMetalContent, LotDetails
from app.schemas import Metal
from app.services.coin_words import US, canonical_country, denom_key, fold, us_denom
from app.services.items import compute_pure_toz

router = APIRouter(prefix="/compositions", tags=["compositions"])


class CompositionOut(BaseModel):
    id: int
    key: str
    label: str
    country: str | None
    denomination: str | None
    year_from: int | None
    year_to: int | None
    mint_marks: list[str] | None
    metal: str
    fineness: Decimal | None
    gross_weight_g: Decimal | None
    pure_toz: Decimal
    per_face_unit: bool
    citation: str | None
    custom: bool


class CompositionIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    metal: Metal
    country: str | None = Field(default=None, max_length=80)
    denomination: str | None = Field(default=None, max_length=80)
    year_from: int | None = None
    year_to: int | None = None
    fineness: Decimal | None = Field(default=None, gt=0, le=1)
    gross_weight_g: Decimal | None = Field(default=None, gt=0)
    pure_toz: Decimal | None = Field(default=None, gt=0)
    per_face_unit: bool = False
    citation: str | None = None


# Words that appear in many labels and so say nothing about which coin it is.
_GENERIC = {"dollar", "dollars", "half", "quarter", "dime", "cent", "cents", "silver", "gold", "coin", "united", "states"}


# what a country's coins are called in English listings vs. on the coin ("Fat Man dollar" = 1 yuan)
_UNIT_SYNONYMS = {"China": {"dollar": "yuan"}}
_OZ_SIZE = re.compile(r"\b\d+(?:/\d+)?\s?oz\b", re.I)


class CompositionMatchOut(CompositionOut):
    score: int


def _out(c: Composition) -> CompositionOut:
    return CompositionOut(**{k: getattr(c, k) for k in CompositionOut.model_fields if k != "custom"}, custom=c.owner_id is not None)


def _visible(principal: Principal):
    return or_(Composition.owner_id.is_(None), Composition.owner_id == principal.owner_id)


@router.get("", response_model=list[CompositionOut])
def list_compositions(
    q: str | None = Query(default=None, max_length=80),
    metal: Metal | None = None,
    per_face: bool | None = None,
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
):
    stmt = select(Composition).where(_visible(principal)).order_by(Composition.per_face_unit, Composition.label)
    if q:
        stmt = stmt.where(or_(Composition.label.ilike(f"%{q}%"), Composition.country.ilike(f"%{q}%")))
    if metal:
        stmt = stmt.where(Composition.metal == metal)
    if per_face is not None:
        stmt = stmt.where(Composition.per_face_unit.is_(per_face))
    return [_out(c) for c in db.scalars(stmt)]


def _comp_denom(c: Composition) -> str | None:
    if not c.denomination:
        return None
    if c.country == US:
        return us_denom(c.denomination) or denom_key(c.denomination)
    return denom_key(c.denomination)


@router.get("/match", response_model=list[CompositionMatchOut])
def match(
    country: str | None = None,
    denomination: str | None = None,
    year: int | None = None,
    mint_mark: str | None = None,
    series: str | None = None,
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
):
    """Suggest compositions for a coin from its details, best first. Equal scores mean the details fit each equally well."""
    country = canonical_country(country)
    us_code = None if country not in (None, US) else (us_denom(denomination) or (None if denomination else us_denom(series)))
    generic = denom_key(denomination)
    for old, new in _UNIT_SYNONYMS.get(country or "", {}).items():
        generic = re.sub(rf"\b{old}\b", new, generic) if generic else generic
    wanted = {k for k in (us_code, generic) if k}
    # "Silver Eagle" must not suggest gold eagles: a metal named in the text rules out the others
    named = re.search(r"\b(gold|silver|platinum|palladium)\b", f"{series or ''} {denomination or ''}".lower())
    metal = {"gold": "Au", "silver": "Ag", "platinum": "Pt", "palladium": "Pd"}[named.group(1)] if named else None
    says_oz = bool(re.search(r"\boz\b|ounce|onza", f"{series or ''} {denomination or ''}".lower()))
    words = [w for w in re.findall(r"[a-z]{4,}", fold(series or "").lower()) if w not in _GENERIC]
    scored: list[tuple[int, Composition]] = []
    for c in db.scalars(select(Composition).where(_visible(principal), Composition.per_face_unit.is_(False))):
        if metal and c.metal != metal:
            continue
        # silver proofs and 40% Bicentennials share years and mint mark with copper-nickel coins
        if c.key.startswith(SILVER_ONLY_PREFIXES) and metal != "Ag":
            continue
        # bullion sized in ounces (the 5 oz America the Beautiful "quarter") only when the text gives a size
        if not says_oz and _OZ_SIZE.search(c.label):
            continue
        score = 0
        if country and c.country:
            if country.lower() != c.country.lower():
                continue
            score += 2
        elif not country and us_code and c.country and c.country != US:
            continue  # "a dime" with no country is a US dime, not a Canadian 10 cents
        if wanted and c.denomination:
            if _comp_denom(c) not in wanted:
                continue
            score += 3
        if year is not None and (c.year_from or c.year_to):
            if (c.year_from and year < c.year_from) or (c.year_to and year > c.year_to):
                continue
            score += 3
        if mint_mark and c.mint_marks:
            if mint_mark.upper() not in c.mint_marks:
                continue
            score += 1
        label = fold(c.label).lower()
        if words and any(w in label for w in words):
            score += 2
        if score >= 5:
            scored.append((score, c))
    scored.sort(key=lambda sc: (-sc[0], sc[1].label))
    return [CompositionMatchOut(**_out(c).model_dump(), score=sc) for sc, c in scored[:5]]


@router.post("", response_model=CompositionOut, status_code=201)
def create_composition(body: CompositionIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    pure = body.pure_toz or compute_pure_toz(body.gross_weight_g, body.fineness)
    if pure is None:
        raise HTTPException(422, "Give the pure weight, or the gross weight and fineness")
    slug = re.sub(r"[^a-z0-9]+", "-", body.label.lower()).strip("-")[:80]
    c = Composition(
        key=f"u{principal.owner_id}-{slug}-{secrets.token_hex(3)}",
        owner_id=principal.owner_id,
        label=body.label,
        country=body.country,
        denomination=body.denomination,
        year_from=body.year_from,
        year_to=body.year_to,
        metal=body.metal,
        fineness=body.fineness,
        gross_weight_g=body.gross_weight_g,
        pure_toz=pure,
        per_face_unit=body.per_face_unit,
        citation=body.citation or "Added by you",
    )
    db.add(c)
    db.commit()
    return _out(c)


@router.delete("/{composition_id}", status_code=204)
def delete_composition(composition_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    c = db.get(Composition, composition_id)
    if c is None or c.owner_id != principal.owner_id:
        raise HTTPException(404, "Only compositions you added can be deleted")
    in_use = db.scalar(select(ItemMetalContent.id).where(ItemMetalContent.composition_id == c.id).limit(1)) or db.scalar(
        select(LotDetails.item_id).where(LotDetails.composition_id == c.id).limit(1)
    )
    if in_use:
        raise HTTPException(409, "Items use this composition; change them first")
    db.delete(c)
    db.commit()
