"""PCGS lookups (by cert number, by PCGS number and grade, or by a PCGS or NGC holder's barcode) to fill a new
item, and the PCGS price guide value for one you own."""

from __future__ import annotations

import re
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.crypto import EncryptionUnavailable
from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Valuation, utcnow
from app.providers import pcgs
from app.providers.base import ProviderError, http_client
from app.schemas import ValuationOut
from app.services import items as item_svc
from app.services import providers as psvc

router = APIRouter(tags=["pcgs"])

BULLION_RE = re.compile(r"bullion|silver eagle|gold eagle|maple|panda|krugerrand|britannia|philharmonic|kangaroo|libertad", re.I)


class LookupIn(BaseModel):
    """One of: a cert number; a PCGS number and grade; or a holder's barcode text and its grading service."""

    cert_no: str | None = Field(default=None, min_length=6, max_length=20)
    pcgs_no: str | None = Field(default=None, max_length=12)
    grade: str | None = Field(default=None, max_length=12)
    barcode: str | None = Field(default=None, max_length=80)
    service: str = "PCGS"

    @model_validator(mode="after")
    def _one(self):
        modes = [bool(self.cert_no), bool(self.pcgs_no or self.grade), bool(self.barcode)]
        if sum(modes) != 1:
            raise ValueError("Give a cert number, or a PCGS number and grade, or a barcode")
        if modes[1] and not (self.pcgs_no and self.grade):
            raise ValueError("Give both the PCGS number and the grade")
        return self


class PcgsCoinOut(BaseModel):
    cert_no: str | None
    pcgs_no: str | None
    name: str | None
    year: int | None
    denomination: str | None
    mint_mark: str | None
    country: str | None
    grade: str | None
    designation: str | None
    metal_content: str | None
    weight_g: Decimal | None
    price_guide: Decimal | None
    population: int | None
    pop_higher: int | None
    coinfacts_link: str | None
    series: str | None
    images: list[dict]


class PcgsLookupOut(BaseModel):
    coin: PcgsCoinOut
    # starting values for the item form, in the same shape as /items/describe
    item_type: str
    title: str
    details: dict
    condition: dict
    metal: dict | None  # {"metal", "gross_weight_g", "fineness"} from PCGS's own figures
    currency_note: str | None


def _call(db: Session, endpoint: str, context: str, fn) -> pcgs.PcgsCoin:
    """One PCGS call through `fn(client, token)`, within the daily cap, logged."""
    cfg = psvc.get_config(db, "pcgs")
    if not cfg.enabled:
        raise HTTPException(409, "PCGS is turned off in Settings, Data providers")
    try:
        token = psvc.api_key(cfg)
    except EncryptionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not token:
        raise HTTPException(409, "Add your PCGS access token in Settings, Data providers first")
    quota = psvc.quota_for(db, cfg)
    if quota is not None and not quota.can_spend(1):
        raise HTTPException(429, "Today's PCGS lookups are used up (your cap in Settings); they reset at midnight UTC")
    with psvc.timed() as t, http_client() as client:
        try:
            coin = fn(client, token)
        except ProviderError as exc:
            if quota is not None and exc.cost:
                quota.record(exc.cost)
            if exc.http_status in (401, 403, 500):
                psvc.mark_failure(cfg, str(exc))
            psvc.log_call(db, "pcgs", endpoint, "error", context=context, http_status=exc.http_status,
                          cost=exc.cost, detail=str(exc), duration_ms=t["ms"])
            db.commit()
            code = {401: 409, 403: 409, 500: 409, 429: 429, 204: 404, 200: 404}.get(exc.http_status or 0, 502)
            raise HTTPException(code if exc.http_status is not None else 422, str(exc)) from exc
    if quota is not None:
        quota.record(1)
    psvc.mark_success(cfg)
    psvc.log_call(db, "pcgs", endpoint, "ok", context=context, cost=1, duration_ms=t["ms"], detail=coin.name)
    db.commit()
    return coin


def by_cert(db: Session, cert_no: str) -> pcgs.PcgsCoin:
    return _call(db, "GetCoinFactsByCertNo", cert_no, lambda c, tok: pcgs.lookup_cert(c, tok, cert_no))


def by_grade(db: Session, pcgs_no: str, grade: str) -> pcgs.PcgsCoin:
    return _call(db, "GetCoinFactsByGrade", f"{pcgs_no} {grade}", lambda c, tok: pcgs.lookup_grade(c, tok, pcgs_no, grade))


def by_barcode(db: Session, barcode: str, service: str) -> pcgs.PcgsCoin:
    return _call(db, "GetCoinFactsByBarcode", f"{service} {barcode}", lambda c, tok: pcgs.lookup_barcode(c, tok, barcode, service))


def _sheldon(grade: str | None) -> int | None:
    m = re.search(r"(\d{1,2})", grade or "")
    return int(m.group(1)) if m and 1 <= int(m.group(1)) <= 70 else None


@router.post("/pcgs/lookup", response_model=PcgsLookupOut)
def lookup(body: LookupIn, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    """One PCGS call. Nothing is saved; the result fills the new-item form."""
    if body.cert_no:
        c, service = by_cert(db, body.cert_no), "PCGS"
    elif body.barcode:
        c, service = by_barcode(db, body.barcode, body.service), body.service
    else:
        c, service = by_grade(db, body.pcgs_no or "", body.grade or ""), None  # a coin type at a grade: not a slab we know
    hay = f"{c.series or ''} {c.name or ''}"
    item_type = "bullion" if BULLION_RE.search(hay) else "coin"
    details = {
        "country": c.country, "denomination": c.denomination, "year": c.year, "mint_mark": c.mint_mark,
        "series": c.series if item_type == "coin" else None, "product_line": c.series if item_type == "bullion" else None,
        "pcgs_number": c.pcgs_no, "diameter_mm": str(c.diameter_mm) if c.diameter_mm else None,
        "variety_notes": None,
    }
    designations = [d.strip() for d in re.split(r"[,/]", c.designation or "") if d.strip()]
    extra = c.designation if c.designation and c.designation not in (c.grade or "") else None
    grade_text = " ".join(x for x in [c.grade, extra] if x)
    metal = None
    parsed = pcgs.parse_metal(c.metal_content)
    if parsed and c.weight_g:
        metal = {"metal": parsed[0], "gross_weight_g": str(c.weight_g), "fineness": str(parsed[1])}
    title = " ".join(x for x in [c.name, service, grade_text] if x)
    condition = {"grading": "slabbed" if service else "raw", "grading_service": service, "cert_number": c.cert_no if service else None,
                 "grade_text": c.grade, "sheldon_grade": _sheldon(c.grade), "designations": designations, "details_reason": None}
    return PcgsLookupOut(
        coin=PcgsCoinOut(**{k: getattr(c, k) for k in PcgsCoinOut.model_fields}),
        item_type=item_type,
        title=title[:300],
        details={k: v for k, v in details.items() if v not in (None, "")},
        condition=condition,
        metal=metal,
        currency_note="PCGS price guide values are in US dollars." if c.price_guide else None,
    )


class BarcodeRead(BaseModel):
    text: str
    format: str


@router.post("/pcgs/read-barcode", response_model=list[BarcodeRead])
async def read_barcode(file: UploadFile = File(...), principal: Principal = Depends(read_items)):
    """The barcodes in a photo of a holder's label, read here on the server (no PCGS call, nothing saved)."""
    from app.services import barcodes

    data = await file.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "That photo is over 25 MB")
    try:
        return barcodes.read(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def price_guide_lookup(db: Session, item) -> pcgs.PcgsCoin:
    """The PCGS data for an item you own: by its PCGS cert, else by its PCGS number and grade (raw or NGC coins)."""
    cond = item.condition
    if cond is not None and (cond.grading_service or "").upper() == "PCGS" and cond.cert_number:
        return by_cert(db, cond.cert_number)
    number = item.coin.pcgs_number if item.coin is not None else None
    grade = (cond.grade_text or (str(cond.sheldon_grade) if cond.sheldon_grade else None)) if cond is not None else None
    if number and grade:
        m = re.search(r"(\d{1,2})\s*(\+)?", grade)
        if m:
            return by_grade(db, number, m.group(1) + (m.group(2) or ""))
    raise HTTPException(422, "This needs a PCGS cert number, or a PCGS number and a grade, filled in on the item")


@router.post("/items/{item_id}/pcgs/price-guide", response_model=ValuationOut, status_code=201)
def price_guide(item_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Saves today's PCGS price guide value as the item's market value (by its cert, or its PCGS number and grade)."""
    item = item_svc.get_item(db, principal, item_id, False)
    if principal.user.base_currency != "USD":
        raise HTTPException(422, "PCGS price guide values are in US dollars; your display currency isn't USD")
    c = price_guide_lookup(db, item)
    if c.price_guide is None:
        raise HTTPException(404, f"PCGS has no price guide value for {c.name or 'this coin'} in {c.grade or 'this grade'}")
    v = price_guide_valuation(item, c)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def price_guide_valuation(item, c: pcgs.PcgsCoin) -> Valuation:
    if item.coin is not None and not item.coin.pcgs_number and c.pcgs_no:
        item.coin.pcgs_number = c.pcgs_no
    pop = f"Population {c.population} at this grade, {c.pop_higher} higher." if c.population is not None else None
    return Valuation(
        item_id=item.id, kind="manual", value_each=c.price_guide, currency="USD", as_of=utcnow().date(),
        source=f"PCGS Price Guide ({c.grade})" if c.grade else "PCGS Price Guide", notes=pop,
        details={"pcgs": {"cert_no": c.cert_no, "pcgs_no": c.pcgs_no, "grade": c.grade, "coinfacts_link": c.coinfacts_link,
                          "population": c.population, "pop_higher": c.pop_higher}},
    )
