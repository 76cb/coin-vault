"""Item CRUD, sale, soft delete/restore and audit history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import (
    AuditLog,
    BanknoteDetails,
    CoinDetails,
    Item,
    ItemCondition,
    ItemMetalContent,
    Location,
    Tag,
    item_tags,
    utcnow,
)
from app.schemas import (
    AuditEntry,
    ItemCreate,
    ItemOut,
    ItemPage,
    ItemStatus,
    ItemType,
    ItemUpdate,
    Metal,
    SaleIn,
)
from app.services import items as svc
from app.services import spot as spot_svc

router = APIRouter(prefix="/items", tags=["items"])

SORTS = {
    "updated": Item.updated_at.desc(),
    "created": Item.created_at.desc(),
    "title": Item.title.asc(),
    "acquired": Item.acquired_date.desc(),
    "year": CoinDetails.year.asc(),
}


def _version_from(if_match: str | None) -> int:
    if not if_match:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "Send If-Match with the item's version")
    try:
        return int(if_match.strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "If-Match must be the item's version number") from exc


def _load(db: Session, principal: Principal, item_id: int, include_deleted: bool = False) -> Item:
    return svc.get_item(db, principal, item_id, include_deleted)


@dataclass
class ItemFilters:
    """The Collection page's filters, shared by the list, the CSV export and the insurance report."""

    q: str | None = None
    item_type: str | None = None
    item_status: str | None = None
    metal: str | None = None
    location_id: int | None = None
    tag: str | None = None
    deleted: bool = False


def item_filters(
    q: str | None = Query(default=None, max_length=100),
    item_type: ItemType | None = Query(default=None, alias="type"),
    item_status: ItemStatus | None = Query(default=None, alias="status"),
    metal: Metal | None = None,
    location_id: int | None = None,
    tag: str | None = None,
    deleted: bool = False,
) -> ItemFilters:
    return ItemFilters(q, item_type, item_status, metal, location_id, tag, deleted)


def filtered_items(owner_id: int, f: ItemFilters):
    """A select of the owner's items matching the filters (joined to coin, banknote and condition details)."""
    stmt = (
        select(Item)
        .outerjoin(CoinDetails, CoinDetails.item_id == Item.id)
        .outerjoin(BanknoteDetails, BanknoteDetails.item_id == Item.id)
        .outerjoin(ItemCondition, ItemCondition.item_id == Item.id)
        .where(Item.owner_id == owner_id)
    )
    stmt = stmt.where(Item.deleted_at.is_not(None) if f.deleted else Item.deleted_at.is_(None))
    if f.item_type:
        stmt = stmt.where(Item.item_type == f.item_type)
    if f.item_status:
        stmt = stmt.where(Item.status == f.item_status)
    if f.location_id is not None:
        stmt = stmt.where(Item.location_id == f.location_id)
    if f.metal:
        stmt = stmt.where(exists().where(ItemMetalContent.item_id == Item.id, ItemMetalContent.metal == f.metal))
    if f.tag:
        stmt = stmt.where(
            exists().where(
                item_tags.c.item_id == Item.id,
                item_tags.c.tag_id == Tag.id,
                func.lower(Tag.name) == f.tag.lower(),
            )
        )
    if f.q:
        q = f.q.strip()
        like = f"%{q}%"
        conds = [
            Item.title.ilike(like),
            Item.notes.ilike(like),
            Item.purchase_source.ilike(like),
            CoinDetails.country.ilike(like),
            CoinDetails.denomination.ilike(like),
            CoinDetails.series.ilike(like),
            CoinDetails.product_line.ilike(like),
            BanknoteDetails.country.ilike(like),
            BanknoteDetails.serial_number.ilike(like),
            ItemCondition.cert_number.ilike(like),
        ]
        if q.isdigit():
            conds.append(CoinDetails.year == int(q))
        stmt = stmt.where(or_(*conds))
    return stmt


ITEM_LOAD = (
    selectinload(Item.tags),
    selectinload(Item.photos),
    selectinload(Item.valuations),
    selectinload(Item.coin),
    selectinload(Item.bar),
    selectinload(Item.banknote),
    selectinload(Item.lot),
    selectinload(Item.other),
    selectinload(Item.condition),
    selectinload(Item.metal_content),
)


@router.get("", response_model=ItemPage)
def list_items(
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
    f: ItemFilters = Depends(item_filters),
    sort: Literal["updated", "created", "title", "acquired", "year"] = "updated",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ItemPage:
    stmt = filtered_items(principal.owner_id, f)
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Item.id).subquery())) or 0
    stmt = (
        stmt.order_by(SORTS[sort], Item.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .options(*ITEM_LOAD)
    )
    rows = db.scalars(stmt).unique().all()
    paths = {
        loc.id: svc.location_path(db, loc.id)
        for loc in db.scalars(select(Location).where(Location.owner_id == principal.owner_id))
    }
    currency = principal.user.base_currency
    spot = spot_svc.spot_map(db, currency)
    return ItemPage(
        items=[svc.list_entry(db, it, paths, spot, currency) for it in rows], total=total, page=page, page_size=page_size
    )


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemCreate, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    item = svc.create_item(db, principal, body)
    db.commit()
    return svc.item_out(db, item)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    return svc.item_out(db, _load(db, principal, item_id, include_deleted=True))


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    body: ItemUpdate,
    if_match: str | None = Header(default=None),
    principal: Principal = Depends(write_items),
    db: Session = Depends(get_db),
):
    item = _load(db, principal, item_id)
    svc.update_item(db, principal, item, body, _version_from(if_match))
    db.commit()
    return svc.item_out(db, item)


@router.post("/{item_id}/sell", response_model=ItemOut)
def sell_item(item_id: int, body: SaleIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    item = _load(db, principal, item_id)
    before = svc.audit_snapshot(item)
    item.status = "sold"
    item.sale_date = body.sale_date
    item.sale_price = body.sale_price
    item.sale_fees = body.sale_fees
    item.sale_venue = body.sale_venue
    item.version += 1
    item.updated_at = utcnow()
    db.flush()
    svc.write_audit(db, principal, item, before, svc.audit_snapshot(item))
    db.commit()
    return svc.item_out(db, item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    item = _load(db, principal, item_id)
    item.deleted_at = utcnow()
    item.version += 1
    svc.audit_event(db, principal, item, "deleted", None, item.deleted_at.isoformat())
    db.commit()


@router.post("/{item_id}/restore", response_model=ItemOut)
def restore_item(item_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    item = _load(db, principal, item_id, include_deleted=True)
    if item.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Item is not deleted")
    svc.audit_event(db, principal, item, "deleted", item.deleted_at.isoformat(), None)
    item.deleted_at = None
    item.version += 1
    db.commit()
    return svc.item_out(db, item)


@router.get("/{item_id}/audit", response_model=list[AuditEntry])
def item_audit(item_id: int, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    item = _load(db, principal, item_id, include_deleted=True)
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity == "item", AuditLog.entity_id == item.id, AuditLog.owner_id == principal.owner_id)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
    )
    return [AuditEntry.model_validate(r) for r in rows]
