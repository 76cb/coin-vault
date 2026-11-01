"""Photo AI through a local Ollama server: identify a piece (and read a grading holder's label), suggest a grade
for a raw coin, and spot pieces you already have. Admins set the server up under Settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items, require_session
from app.providers import ollama
from app.routers.describe import DescribeOut, described_out
from app.schemas import PhotoRole, _Base
from app.services import ai
from app.services import items as item_svc
from app.services.describe import describe
from app.services.providers import get_system, set_system

router = APIRouter(prefix="/ai", tags=["ai"])


def require_admin(principal: Principal = Depends(require_session)) -> Principal:
    if not principal.user.is_admin:
        raise HTTPException(403, "Only an admin can set up the AI server")
    return principal


# --- Settings ----------------------------------------------------------------------------------


class AiStatus(BaseModel):
    ready: bool
    model: str | None


class AiSettingsOut(AiStatus):
    url: str


class AiSettingsIn(BaseModel):
    url: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=120)


class CheckIn(BaseModel):
    url: str = Field(max_length=200)


class ModelOut(BaseModel):
    name: str
    size: int | None
    parameter_size: str | None
    quantization: str | None
    vision: bool


class CheckOut(BaseModel):
    url: str
    version: str
    models: list[ModelOut]


@router.get("", response_model=AiStatus)
def status(principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    """Whether photo AI is ready to use (so pages know to offer it)."""
    s = ai.configured(db)
    return AiStatus(ready=s is not None, model=s[1] if s else None)


@router.get("/settings", response_model=AiSettingsOut)
def get_settings_(principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    url, model = str(get_system(db, "ai_url") or ""), str(get_system(db, "ai_model") or "")
    return AiSettingsOut(url=url, model=model or None, ready=bool(url and model))


@router.put("/settings", response_model=AiSettingsOut)
def save_settings(body: AiSettingsIn, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    """Save the server and model; an empty address turns photo AI off."""
    url = ""
    if body.url.strip():
        try:
            url = ollama.clean_url(body.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not body.model.strip():
            raise HTTPException(422, "Choose a model that can see photos")
    model = body.model.strip() if url else ""
    set_system(db, "ai_url", url)
    set_system(db, "ai_model", model)
    db.commit()
    return AiSettingsOut(url=url, model=model or None, ready=bool(url and model))


@router.post("/check", response_model=CheckOut)
def check(body: CheckIn, principal: Principal = Depends(require_admin)):
    """Talk to the server at this address: its version and the models it has, marked by whether they see photos."""
    try:
        url = ollama.clean_url(body.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        with ollama.client(ollama.LIST_SECONDS) as c:
            v = ollama.version(c, url)
            ms = ollama.models(c, url)
    except ollama.OllamaError as exc:
        raise HTTPException(502, str(exc)) from exc
    return CheckOut(url=url, version=v, models=[ModelOut(**m.__dict__) for m in ms])


# --- Looking at photos -------------------------------------------------------------------------


class AiPhotoIn(_Base):
    sha256: str = Field(min_length=64, max_length=64)
    role: PhotoRole = "other"


class PhotosIn(_Base):
    photos: list[AiPhotoIn] = Field(min_length=1, max_length=12)
    item_id: int | None = None  # the item these are on: its edited copies are used, and it isn't its own match


class HolderOut(BaseModel):
    service: str | None
    grade: str | None
    cert_number: str | None
    pcgs_number: str | None
    label_text: str | None


class MatchOut(BaseModel):
    id: int
    title: str
    thumb: str | None
    quantity: int
    why: str  # what matched, or "exact" / "similar" for the same photo


class IdentifyOut(BaseModel):
    model: str
    seconds: float
    load_seconds: float
    confidence: str
    title: str
    kind: str
    country: str | None
    denomination: str | None
    year: int | None
    mint_mark: str | None
    series: str | None
    weight_text: str | None
    holder: HolderOut | None
    barcodes: list[dict[str, str]]
    notes: str | None
    described: DescribeOut  # starting values for the item form, the same shape as /items/describe
    same_coin: list[MatchOut]
    same_photos: list[MatchOut]


class GradeOut(BaseModel):
    model: str
    seconds: float
    low: str
    high: str
    low_number: int
    high_number: int
    summary: str
    wear: str | None
    surfaces: str | None
    marks: list[str]
    problems: list[str]
    photo_advice: str | None


def _sources(db: Session, principal: Principal, body: PhotosIn) -> list[ai.Source]:
    if body.item_id is not None:
        item_svc.get_item(db, principal, body.item_id)  # 404 unless it's yours
    try:
        return ai.sources(db, principal.owner_id, [(p.sha256, p.role) for p in body.photos], body.item_id)
    except ai.PhotoMissing as exc:
        raise HTTPException(404, str(exc)) from exc


def _run(fn):
    try:
        return fn()
    except ai.AiNotSet as exc:
        raise HTTPException(503, str(exc)) from exc
    except ollama.OllamaError as exc:
        raise HTTPException(502, str(exc)) from exc


DETAIL_KEYS = {
    "coin": ("country", "denomination", "year", "mint_mark", "series"),
    "bullion": ("country", "denomination", "year", "mint_mark"),
    "banknote": ("country", "denomination"),
}


def _form_values(db: Session, principal: Principal, i: ai.Identified) -> DescribeOut:
    """What the title reader makes of the model's title, with the gaps filled from what the model read directly."""
    d = describe(ai.listing_title(i))
    if i.kind in ("bar", "banknote", "other") and d.item_type != i.kind and not d.recognized:
        d.item_type = i.kind
        d.details = {}
    if i.kind == "bar" and d.item_type == "coin":
        d.item_type, d.details = "bar", {}
    for key in DETAIL_KEYS.get(d.item_type, ()):
        value = getattr(i, key)
        if value not in (None, "") and not d.details.get(key):
            d.details[key] = value
    if d.item_type == "bullion" and not d.details.get("product_line") and i.series:
        d.details["product_line"] = i.series
    if d.metal is None:
        d.metal = i.metal
    h = i.holder
    if h is not None:
        if d.condition is None or d.condition.get("grading") != "slabbed":
            g = ai._grade(h.grade or "")
            d.condition = {
                "grading": "slabbed", "grading_service": h.service, "grade_text": g[0] if g else h.grade,
                "sheldon_grade": g[1] if g else None, "designations": [], "details_reason": "Details grade" if "detail" in (h.grade or "").lower() else None,
            }
        if h.cert_number:
            d.condition["cert_number"] = h.cert_number
            d.recognized.append(f"cert {h.cert_number}")
        if h.pcgs_number and d.item_type in ("coin", "bullion"):
            d.details["pcgs_number"] = h.pcgs_number
    return described_out(db, principal, d)


def _match(it, why: str) -> MatchOut:
    return MatchOut(id=it.id, title=it.title, thumb=item_svc.cover_thumb(it), quantity=it.quantity, why=why)


@router.post("/identify", response_model=IdentifyOut)
def identify(body: PhotosIn, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    """What the piece in these photos is, as starting values for the form; slab labels and barcodes are read too.
    Nothing is saved."""
    srcs = _sources(db, principal, body)
    i = _run(lambda: ai.identify(db, srcs))
    form = _form_values(db, principal, i)
    ident = {**form.details, "year": form.details.get("year") or i.year, "series": form.details.get("series") or i.series}
    return IdentifyOut(
        model=ai.configured(db)[1],  # type: ignore[index]
        seconds=round(i.seconds, 1), load_seconds=round(i.load_seconds, 1), confidence=i.confidence, title=i.title,
        kind=i.kind, country=i.country, denomination=i.denomination, year=i.year, mint_mark=i.mint_mark, series=i.series,
        weight_text=i.weight_text, holder=HolderOut(**i.holder.__dict__) if i.holder else None, barcodes=i.barcodes,
        notes=i.notes, described=form,
        same_coin=[_match(m.item, m.why) for m in ai.same_coin(db, principal.owner_id, ident, body.item_id)],
        same_photos=[_match(it, kind) for it, kind in ai.same_photos(db, principal.owner_id, srcs, body.item_id)],
    )


@router.post("/grade", response_model=GradeOut)
def grade(body: PhotosIn, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    """A rough grade range for a raw coin from its photos. A guess to guide you, not a grade."""
    srcs = _sources(db, principal, body)
    item = item_svc.get_item(db, principal, body.item_id) if body.item_id is not None else None
    g = _run(lambda: ai.suggest_grade(db, srcs, item))
    return GradeOut(model=ai.configured(db)[1], **{**g.__dict__, "seconds": round(g.seconds, 1)})  # type: ignore[index]
