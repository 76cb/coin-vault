"""Storage locations and tags."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Item, Location, Tag, item_tags
from app.schemas import LocationIn, LocationOut, TagIn, TagOut
from app.services import items as svc

router = APIRouter(tags=["reference"])


def _location(db: Session, principal: Principal, location_id: int) -> Location:
    loc = db.get(Location, location_id)
    if loc is None or loc.owner_id != principal.owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    return loc


def _check_parent(db: Session, principal: Principal, loc_id: int | None, parent_id: int | None) -> None:
    if parent_id is None:
        return
    parent = _location(db, principal, parent_id)
    seen: set[int] = set()
    while parent is not None:
        if parent.id == loc_id or parent.id in seen:
            raise HTTPException(422, "A location cannot be inside itself")
        seen.add(parent.id)
        parent = db.get(Location, parent.parent_id) if parent.parent_id else None


def _loc_out(db: Session, loc: Location, counts: dict[int, int]) -> LocationOut:
    return LocationOut(
        id=loc.id,
        name=loc.name,
        parent_id=loc.parent_id,
        notes=loc.notes,
        path=svc.location_path(db, loc.id) or loc.name,
        item_count=counts.get(loc.id, 0),
    )


@router.get("/locations", response_model=list[LocationOut])
def list_locations(principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    counts = svc.item_count_by_location(db, principal.owner_id)
    locs = db.scalars(select(Location).where(Location.owner_id == principal.owner_id)).all()
    out = [_loc_out(db, loc, counts) for loc in locs]
    return sorted(out, key=lambda o: o.path.lower())


@router.post("/locations", response_model=LocationOut, status_code=201)
def create_location(body: LocationIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    _check_parent(db, principal, None, body.parent_id)
    loc = Location(owner_id=principal.owner_id, **body.model_dump())
    db.add(loc)
    db.commit()
    return _loc_out(db, loc, {})


@router.patch("/locations/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int, body: LocationIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)
):
    loc = _location(db, principal, location_id)
    _check_parent(db, principal, loc.id, body.parent_id)
    for k, v in body.model_dump().items():
        setattr(loc, k, v)
    db.commit()
    return _loc_out(db, loc, svc.item_count_by_location(db, principal.owner_id))


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    loc = _location(db, principal, location_id)
    in_use = db.scalar(select(func.count()).select_from(Item).where(Item.location_id == loc.id, Item.deleted_at.is_(None)))
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{in_use} item(s) are stored here; move them first")
    children = db.scalars(select(Location).where(Location.parent_id == loc.id)).all()
    for child in children:
        child.parent_id = loc.parent_id
    db.delete(loc)
    db.commit()


def _tag_counts(db: Session, owner_id: int) -> dict[int, int]:
    rows = db.execute(
        select(item_tags.c.tag_id, func.count())
        .join(Item, Item.id == item_tags.c.item_id)
        .where(Item.owner_id == owner_id, Item.deleted_at.is_(None))
        .group_by(item_tags.c.tag_id)
    )
    return {t: n for t, n in rows}


@router.get("/tags", response_model=list[TagOut])
def list_tags(principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    counts = _tag_counts(db, principal.owner_id)
    tags = db.scalars(select(Tag).where(Tag.owner_id == principal.owner_id).order_by(func.lower(Tag.name)))
    return [TagOut(id=t.id, name=t.name, item_count=counts.get(t.id, 0)) for t in tags]


@router.post("/tags", response_model=TagOut, status_code=201)
def create_tag(body: TagIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    tag = svc.resolve_tags(db, principal.owner_id, [body.name])[0]
    db.commit()
    return TagOut(id=tag.id, name=tag.name, item_count=_tag_counts(db, principal.owner_id).get(tag.id, 0))


@router.patch("/tags/{tag_id}", response_model=TagOut)
def rename_tag(tag_id: int, body: TagIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    tag = db.get(Tag, tag_id)
    if tag is None or tag.owner_id != principal.owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    clash = db.scalar(
        select(Tag).where(Tag.owner_id == principal.owner_id, func.lower(Tag.name) == body.name.lower(), Tag.id != tag.id)
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "A tag with that name already exists")
    tag.name = body.name
    db.commit()
    return TagOut(id=tag.id, name=tag.name, item_count=_tag_counts(db, principal.owner_id).get(tag.id, 0))


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    tag = db.get(Tag, tag_id)
    if tag is None or tag.owner_id != principal.owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    db.delete(tag)
    db.commit()
