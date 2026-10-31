"""Item business logic: create/update with type-specific details, metal content, tags and audit."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import Principal, request_id_var
from app.services import spot as spot_svc
from app.services import valuation
from app.services.photo_edit import edit_hash
from app.models import (
    User,
    AuditLog,
    BanknoteDetails,
    BarDetails,
    CoinDetails,
    Composition,
    Document,
    Item,
    ItemCondition,
    ItemMetalContent,
    Location,
    LotDetails,
    OtherDetails,
    Photo,
    Tag,
    document_links,
    utcnow,
)
from app.schemas import (
    DETAIL_MODELS,
    ConditionIn,
    DocumentSummary,
    ItemCreate,
    ItemListEntry,
    ItemOut,
    ItemUpdate,
    ItemValuesOut,
    MetalContentIn,
    MetalContentOut,
    PhotoOut,
)

TROY_OUNCE_G = Decimal("31.1034768")
UNIT_GRAMS = {"g": Decimal(1), "ozt": TROY_OUNCE_G, "kg": Decimal(1000), "tola": Decimal("11.6638038")}
PURE_QUANT = Decimal("0.000001")

DETAIL_ATTR = {"coin": "coin", "bullion": "coin", "bar": "bar", "banknote": "banknote", "lot": "lot", "other": "other"}
DETAIL_CLASS = {
    "coin": CoinDetails,
    "bar": BarDetails,
    "banknote": BanknoteDetails,
    "lot": LotDetails,
    "other": OtherDetails,
}

# Value-affecting fields recorded in the audit log.
AUDITED_FIELDS = (
    "item_type",
    "quantity",
    "status",
    "purchase_price",
    "purchase_fees",
    "cost_basis_status",
    "valuation_rule",
    "sale_date",
    "sale_price",
    "sale_fees",
)


# --- URLs ------------------------------------------------------------------------------



def photo_urls(photo_id: int, edits: dict | None = None) -> dict[str, str]:
    """Edited photos get a version in their display URLs, so browsers don't keep showing a cached copy."""
    base = f"/api/v1/media/photos/{photo_id}"
    v = f"?v={edit_hash(edits)}" if edits else ""
    urls = {"thumb": f"{base}/thumb{v}", "medium": f"{base}/medium{v}", "original": f"{base}/original"}
    if edits:
        urls["unedited"] = f"{base}/unedited"
        urls["edited"] = f"{base}/edited{v}"
    else:
        urls["unedited"] = f"{base}/medium"
    return urls


def upload_file_urls(file_id: int) -> dict[str, str]:
    base = f"/api/v1/media/uploads/{file_id}"
    return {"thumb": f"{base}/thumb", "medium": f"{base}/medium", "original": f"{base}/original"}


def document_url(doc_id: int) -> str:
    return f"/api/v1/documents/{doc_id}/file"


# --- Helpers ---------------------------------------------------------------------------


def grams_to_toz(grams: Decimal) -> Decimal:
    return grams / TROY_OUNCE_G


def compute_pure_toz(gross_g: Decimal | None, fineness: Decimal | None) -> Decimal | None:
    if gross_g is None or fineness is None:
        return None
    return (grams_to_toz(gross_g) * fineness).quantize(PURE_QUANT, rounding=ROUND_HALF_UP)


def location_path(db: Session, location_id: int | None) -> str | None:
    if location_id is None:
        return None
    names: list[str] = []
    seen: set[int] = set()
    current = db.get(Location, location_id)
    while current is not None and current.id not in seen and len(names) < 20:
        seen.add(current.id)
        names.append(current.name)
        current = db.get(Location, current.parent_id) if current.parent_id else None
    return " › ".join(reversed(names))


def owned_location(db: Session, owner_id: int, location_id: int | None) -> Location | None:
    if location_id is None:
        return None
    loc = db.get(Location, location_id)
    if loc is None or loc.owner_id != owner_id:
        raise HTTPException(422, "Unknown location")
    return loc


def get_item(db: Session, principal: Principal, item_id: int, include_deleted: bool = False) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.owner_id != principal.owner_id or (item.deleted_at and not include_deleted):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


def resolve_tags(db: Session, owner_id: int, names: list[str]) -> list[Tag]:
    existing = {t.name.lower(): t for t in db.scalars(select(Tag).where(Tag.owner_id == owner_id))}
    out: list[Tag] = []
    for name in names:
        tag = existing.get(name.lower())
        if tag is None:
            tag = Tag(owner_id=owner_id, name=name)
            db.add(tag)
            existing[name.lower()] = tag
        out.append(tag)
    return out


def _validate_details(item_type: str, details: dict[str, Any] | None) -> dict[str, Any]:
    model = DETAIL_MODELS[item_type]
    try:
        return model.model_validate(details or {}).model_dump()
    except ValidationError as exc:
        raise HTTPException(
            422,
            [{**e, "loc": ["body", "details", *e["loc"]]} for e in exc.errors(include_url=False, include_context=False)],
        ) from exc


def _apply_details(db: Session, item: Item, details: dict[str, Any] | None, replace: bool) -> None:
    attr = DETAIL_ATTR[item.item_type]
    # Remove detail rows belonging to other types (e.g. after a type change).
    for other_attr in set(DETAIL_ATTR.values()) - {attr}:
        if getattr(item, other_attr) is not None:
            setattr(item, other_attr, None)
    current = getattr(item, attr)
    if details is None and current is not None and not replace:
        return
    base: dict[str, Any] = {}
    if current is not None and not replace:
        base = {c.key: getattr(current, c.key) for c in current.__table__.columns if c.key != "item_id"}
    merged = _validate_details(item.item_type, {**base, **(details or {})})
    if item.item_type == "lot" and merged.get("composition_id"):
        comp = db.get(Composition, merged["composition_id"])
        if comp is None:
            raise HTTPException(422, "Unknown composition")
    cls = DETAIL_CLASS[attr]
    if current is None:
        setattr(item, attr, cls(**merged))
    else:
        for k, v in merged.items():
            setattr(current, k, v)


def _apply_condition(item: Item, condition: ConditionIn | None) -> None:
    if condition is None:
        item.condition = None
        return
    data = condition.model_dump()
    if item.condition is None:
        item.condition = ItemCondition(**data)
    else:
        for k, v in data.items():
            setattr(item.condition, k, v)


def _apply_metal_content(db: Session, item: Item, rows: list[MetalContentIn]) -> None:
    item.metal_content.clear()
    db.flush()
    for row in rows:
        gross = row.gross_weight_g
        fineness = row.fineness
        if gross is None and item.item_type == "bar" and item.bar and item.bar.weight_value:
            gross = item.bar.weight_value * UNIT_GRAMS[item.bar.weight_unit]
        comp = None
        if row.composition_id is not None:
            comp = db.get(Composition, row.composition_id)
            if comp is None:
                raise HTTPException(422, "Unknown composition")
            if comp.per_face_unit:
                raise HTTPException(422, "Per-face compositions apply to lots; pick it in the lot details instead")
        if row.pure_toz is not None:
            pure, source = row.pure_toz, "override"
        elif comp is not None and gross is None and fineness is None:
            # Standard composition: use the reference table's actual metal weight.
            gross, fineness, pure, source = comp.gross_weight_g, comp.fineness, comp.pure_toz, "reference"
        else:
            pure, source = compute_pure_toz(gross, fineness), "computed"
        item.metal_content.append(
            ItemMetalContent(
                metal=comp.metal if comp is not None and source == "reference" else row.metal,
                gross_weight_g=gross,
                fineness=fineness,
                pure_toz=pure,
                source=source,
                composition_id=row.composition_id,
            )
        )


def _metal_summary(item: Item) -> str:
    return json.dumps(
        [[m.metal, str(m.gross_weight_g), str(m.fineness), str(m.pure_toz), m.source] for m in item.metal_content]
    )


def _condition_summary(item: Item) -> str | None:
    c = item.condition
    if c is None:
        return None
    return json.dumps([c.grading, c.sheldon_grade, c.grade_text, c.grading_service, c.cert_number, c.designations])


def audit_snapshot(item: Item) -> dict[str, str | None]:
    snap = {f: _fmt(getattr(item, f)) for f in AUDITED_FIELDS}
    snap["condition"] = _condition_summary(item)
    snap["metal_content"] = _metal_summary(item)
    return snap


def _fmt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    return str(v)


def write_audit(
    db: Session, principal: Principal, item: Item, before: dict[str, str | None], after: dict[str, str | None]
) -> None:
    actor_type, actor_id = principal.actor
    rid = request_id_var.get()
    for field_name, new in after.items():
        old = before.get(field_name)
        if old != new:
            db.add(
                AuditLog(
                    owner_id=item.owner_id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    entity="item",
                    entity_id=item.id,
                    field=field_name,
                    old_value=old,
                    new_value=new,
                    request_id=rid,
                )
            )


def audit_event(db: Session, principal: Principal, item: Item, field_name: str, old: str | None, new: str | None):
    actor_type, actor_id = principal.actor
    db.add(
        AuditLog(
            owner_id=item.owner_id,
            actor_type=actor_type,
            actor_id=actor_id,
            entity="item",
            entity_id=item.id,
            field=field_name,
            old_value=old,
            new_value=new,
            request_id=request_id_var.get(),
        )
    )


# --- Create / update -------------------------------------------------------------------

SIMPLE_FIELDS = (
    "title",
    "quantity",
    "status",
    "acquired_date",
    "purchase_price",
    "purchase_fees",
    "purchase_source",
    "notes",
    "valuation_rule",
    "sale_date",
    "sale_price",
    "sale_fees",
    "sale_venue",
)
NOT_NULLABLE = {"title", "quantity", "status", "valuation_rule", "cost_basis_status", "item_type"}


def _check_sale(item: Item) -> None:
    if item.status == "sold" and (item.sale_date is None or item.sale_price is None):
        raise HTTPException(422, "A sold item needs a sale date and sale price")


def create_item(db: Session, principal: Principal, body: ItemCreate) -> Item:
    data = body.model_dump(exclude_unset=True)
    owned_location(db, principal.owner_id, data.get("location_id"))
    item = Item(owner_id=principal.owner_id, item_type=body.item_type, title=body.title, quantity=body.quantity)
    for f in SIMPLE_FIELDS:
        if f in data and data[f] is not None:
            setattr(item, f, data[f])
    item.location_id = data.get("location_id")
    item.cost_basis_status = body.cost_basis_status or ("known" if body.purchase_price is not None else "unknown")
    _check_sale(item)
    db.add(item)
    db.flush()
    _apply_details(db, item, body.details, replace=True)
    if body.condition is not None:
        _apply_condition(item, body.condition)
    if body.metal_content:
        _apply_metal_content(db, item, body.metal_content)
    if body.tags:
        item.tags = resolve_tags(db, principal.owner_id, body.tags)
    db.flush()
    write_audit(db, principal, item, {}, {k: v for k, v in audit_snapshot(item).items() if v not in (None, "[]")})
    return item


def update_item(db: Session, principal: Principal, item: Item, body: ItemUpdate, expected_version: int) -> Item:
    if item.version != expected_version:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            f"Item changed since you loaded it (now version {item.version}); reload and try again",
        )
    data = body.model_dump(exclude_unset=True)
    for f in NOT_NULLABLE:
        if f in data and data[f] is None:
            raise HTTPException(422, f"{f} cannot be empty")
    before = audit_snapshot(item)
    if "location_id" in data:
        owned_location(db, principal.owner_id, data["location_id"])
        item.location_id = data["location_id"]
    for f in SIMPLE_FIELDS:
        if f in data:
            setattr(item, f, data[f])
    type_changed = "item_type" in data and data["item_type"] != item.item_type
    if "item_type" in data:
        item.item_type = data["item_type"]
    if "cost_basis_status" in data:
        item.cost_basis_status = data["cost_basis_status"]
    elif "purchase_price" in data:
        if data["purchase_price"] is None:
            item.cost_basis_status = "unknown"
        elif item.cost_basis_status == "unknown":
            item.cost_basis_status = "known"
    _check_sale(item)
    if "details" in data or type_changed:
        _apply_details(db, item, data.get("details"), replace=type_changed)
    if "condition" in data:
        _apply_condition(item, body.condition)
    if "metal_content" in data:
        _apply_metal_content(db, item, body.metal_content or [])
    if "tags" in data:
        item.tags = resolve_tags(db, principal.owner_id, body.tags or [])
    item.version += 1
    item.updated_at = utcnow()
    db.flush()
    write_audit(db, principal, item, before, audit_snapshot(item))
    return item


# --- Serialisation ---------------------------------------------------------------------


def cost_basis(item: Item) -> Decimal | None:
    if item.purchase_price is None:
        return None
    return item.purchase_price + (item.purchase_fees or Decimal(0))


def _details_dict(item: Item) -> dict[str, Any]:
    row = getattr(item, DETAIL_ATTR[item.item_type])
    if row is None:
        return DETAIL_MODELS[item.item_type]().model_dump()
    return {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key != "item_id"}


def _grade_label(item: Item) -> str | None:
    c = item.condition
    if c is None:
        return None
    parts = []
    if c.grading == "slabbed" and c.grading_service:
        parts.append(c.grading_service)
    if c.grade_text:
        parts.append(c.grade_text)
    elif c.sheldon_grade:
        parts.append(str(c.sheldon_grade))
    parts.extend(c.designations or [])
    return " ".join(parts) or None


def _photo_out(p: Photo) -> PhotoOut:
    return PhotoOut(
        id=p.id,
        item_id=p.item_id,
        role=p.role,
        sort_order=p.sort_order,
        width=p.width,
        height=p.height,
        bytes=p.bytes,
        mime=p.mime,
        quality=p.quality or {},
        original_filename=p.original_filename,
        created_at=p.created_at,
        urls=photo_urls(p.id, p.edits),
        edits=p.edits,
        sha256=p.sha256,
    )


def photo_out(p: Photo) -> PhotoOut:
    return _photo_out(p)


def cover_thumb(item: Item) -> str | None:
    photo = next((p for p in item.photos if p.id == item.cover_photo_id), None) or (item.photos[0] if item.photos else None)
    return photo_urls(photo.id, photo.edits)["thumb"] if photo else None


def values_out(db: Session, item: Item, currency: str, spot: dict) -> ItemValuesOut:
    v = valuation.item_values(db, item, spot, currency=currency)
    mv = v.market_valuation
    return ItemValuesOut(
        currency=currency,
        melt=v.melt,
        melt_by_metal=v.melt_by_metal,
        melt_missing_spot=v.melt_missing_spot,
        market=v.market,
        market_each=mv.value_each if mv else None,
        market_as_of=mv.as_of if mv else None,
        market_kind=mv.kind if mv else None,
        market_source=mv.source if mv else None,
        cost=v.cost,
        current=v.current,
        gain=v.gain,
        rule=v.rule,
        rule_applied=v.rule_applied,
        pure_toz_total=v.pure_toz_total,
    )


def owner_currency(db: Session, owner_id: int) -> str:
    user = db.get(User, owner_id)
    return user.base_currency if user else "USD"


def item_out(db: Session, item: Item, spot: dict | None = None) -> ItemOut:
    currency = owner_currency(db, item.owner_id)
    if spot is None:
        spot = spot_svc.spot_map(db, currency)
    docs = db.scalars(
        select(Document)
        .join(document_links, document_links.c.document_id == Document.id)
        .where(document_links.c.item_id == item.id)
        .order_by(Document.created_at.desc())
    ).all()
    return ItemOut(
        id=item.id,
        item_type=item.item_type,
        title=item.title,
        quantity=item.quantity,
        status=item.status,
        location_id=item.location_id,
        location_path=location_path(db, item.location_id),
        acquired_date=item.acquired_date,
        purchase_price=item.purchase_price,
        purchase_fees=item.purchase_fees,
        cost_basis=cost_basis(item),
        cost_basis_status=item.cost_basis_status,
        purchase_source=item.purchase_source,
        notes=item.notes,
        valuation_rule=item.valuation_rule,
        sale_date=item.sale_date,
        sale_price=item.sale_price,
        sale_fees=item.sale_fees,
        sale_venue=item.sale_venue,
        condition=ConditionIn.model_validate(item.condition) if item.condition else None,
        details=_details_dict(item),
        metal_content=[MetalContentOut.model_validate(m) for m in item.metal_content],
        pure_toz_per_unit=valuation.pure_per_unit(db, item),
        values=values_out(db, item, currency, spot),
        tags=[t.name for t in item.tags],
        cover_photo_id=item.cover_photo_id,
        cover_thumb_url=cover_thumb(item),
        photos=[_photo_out(p) for p in item.photos],
        documents=[
            DocumentSummary(id=d.id, kind=d.kind, title=d.title, doc_date=d.doc_date, mime=d.mime, url=document_url(d.id))
            for d in docs
        ],
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )


def list_entry(
    db: Session, item: Item, paths: dict[int, str | None], spot: dict | None = None, currency: str = "USD"
) -> ItemListEntry:
    v = valuation.item_values(db, item, spot or {}, currency=currency)
    coin = item.coin if item.item_type in ("coin", "bullion") else None
    country = coin.country if coin else (item.banknote.country if item.banknote else None)
    return ItemListEntry(
        id=item.id,
        item_type=item.item_type,
        title=item.title,
        quantity=item.quantity,
        status=item.status,
        location_path=paths.get(item.location_id) if item.location_id else None,
        year=coin.year if coin else None,
        country=country,
        grade=_grade_label(item),
        cost_basis=cost_basis(item),
        cost_basis_status=item.cost_basis_status,
        tags=[t.name for t in item.tags],
        cover_thumb_url=cover_thumb(item),
        photo_count=len(item.photos),
        melt=v.melt,
        current=v.current,
        currency=currency,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )


def item_count_by_location(db: Session, owner_id: int) -> dict[int, int]:
    rows = db.execute(
        select(Item.location_id, func.count())
        .where(Item.owner_id == owner_id, Item.deleted_at.is_(None), Item.location_id.is_not(None))
        .group_by(Item.location_id)
    )
    return {loc: n for loc, n in rows}
