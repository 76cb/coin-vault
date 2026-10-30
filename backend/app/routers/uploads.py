"""Bulk photo upload: files are processed, auto-paired into groups, then attached or turned into items."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Photo, UploadGroup, utcnow
from app.models import UploadFile as UploadFileRow
from app.schemas import (
    GroupAttach,
    GroupCreateItem,
    GroupMerge,
    GroupPatch,
    ItemOut,
    UploadFileOut,
    UploadGroupOut,
    UploadResult,
)
from app.services import items as item_svc
from app.services import media
from app.services.images import IntakeError, StoredImage, store_image
from app.services.pairing import plan_groups

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _group(db: Session, principal: Principal, group_id: int, pending: bool = True) -> UploadGroup:
    g = db.get(UploadGroup, group_id)
    if g is None or g.owner_id != principal.owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload group not found")
    if pending and g.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This group is already {g.status.replace('_', ' ')}")
    return g


def _file_out(db: Session, f: UploadFileRow) -> UploadFileOut:
    dup_item = None
    if f.duplicate_of_photo_id:
        photo = db.get(Photo, f.duplicate_of_photo_id)
        dup_item = photo.item_id if photo else None
    return UploadFileOut(
        id=f.id,
        seq=f.seq,
        original_filename=f.original_filename,
        role=f.suggested_role,
        width=f.width,
        height=f.height,
        bytes=f.bytes,
        quality=f.quality or {},
        duplicate_of_photo_id=f.duplicate_of_photo_id,
        duplicate_of_item_id=dup_item,
        duplicate_kind=f.duplicate_kind,
        urls=item_svc.upload_file_urls(f.id),
    )


def _group_out(db: Session, g: UploadGroup) -> UploadGroupOut:
    return UploadGroupOut(
        id=g.id,
        batch_id=g.batch_id,
        pairing_rule=g.pairing_rule,
        label=g.label,
        status=g.status,
        resulting_item_id=g.resulting_item_id,
        created_at=g.created_at,
        files=[_file_out(db, f) for f in g.files],
    )


@router.post("", response_model=UploadResult, status_code=201)
async def bulk_upload(
    files: Annotated[list[UploadFile], File(description="Photos to pair into items")],
    principal: Principal = Depends(write_items),
    db: Session = Depends(get_db),
):
    s = get_settings()
    if not files:
        raise HTTPException(422, "No files sent")
    if len(files) > s.max_files_per_upload:
        raise HTTPException(413, f"At most {s.max_files_per_upload} files at once")
    max_bytes = s.max_photo_mb * 1024 * 1024
    accepted: list[tuple[str, object]] = []
    rejected: list[dict[str, str]] = []
    for up in files:
        name = (up.filename or "upload").replace("\\", "/").split("/")[-1][:255]
        try:
            data = await media.read_limited(up, max_bytes)
            stored = store_image(data, max_bytes)
        except IntakeError as exc:
            rejected.append({"filename": name, "reason": str(exc)})
            continue
        except HTTPException as exc:
            rejected.append({"filename": name, "reason": str(exc.detail)})
            continue
        accepted.append((name, stored))

    batch_id = str(uuid.uuid4())
    groups: list[UploadGroup] = []
    for plan in plan_groups([n for n, _ in accepted]):
        group = UploadGroup(owner_id=principal.owner_id, batch_id=batch_id, pairing_rule=plan.rule, label=plan.label)
        for seq, (idx, role) in enumerate(plan.members):
            name, stored = accepted[idx]
            dup = media.find_duplicate(db, principal.owner_id, stored)
            group.files.append(
                UploadFileRow(
                    owner_id=principal.owner_id,
                    seq=seq,
                    original_filename=name,
                    storage_key=stored.storage_key,
                    sha256=stored.sha256,
                    phash=stored.phash,
                    mime=stored.mime,
                    width=stored.width,
                    height=stored.height,
                    bytes=stored.bytes,
                    quality=stored.quality,
                    suggested_role=role,
                    duplicate_of_photo_id=dup[0] if dup else None,
                    duplicate_kind=dup[2] if dup else None,
                )
            )
        db.add(group)
        groups.append(group)
    db.commit()
    return UploadResult(batch_id=batch_id, groups=[_group_out(db, g) for g in groups], rejected=rejected)


@router.get("/groups", response_model=list[UploadGroupOut])
def list_groups(
    group_status: Literal["pending", "attached", "created_item", "discarded", "all"] = Query("pending", alias="status"),
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
):
    stmt = (
        select(UploadGroup)
        .where(UploadGroup.owner_id == principal.owner_id)
        .options(selectinload(UploadGroup.files))
        .order_by(UploadGroup.created_at.desc(), UploadGroup.id)
    )
    if group_status != "all":
        stmt = stmt.where(UploadGroup.status == group_status)
    return [_group_out(db, g) for g in db.scalars(stmt)]


@router.patch("/groups/{group_id}", response_model=UploadGroupOut)
def patch_group(group_id: int, body: GroupPatch, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    g = _group(db, principal, group_id)
    data = body.model_dump(exclude_unset=True)
    if "label" in data:
        g.label = data["label"]
    if body.roles:
        by_id = {f.id: f for f in g.files}
        unknown = set(body.roles) - set(by_id)
        if unknown:
            raise HTTPException(422, "Some files are not in this group")
        for fid, role in body.roles.items():
            by_id[fid].suggested_role = role
        g.pairing_rule = "manual"
    db.commit()
    return _group_out(db, g)


@router.post("/groups/{group_id}/split", response_model=list[UploadGroupOut])
def split_group(group_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    g = _group(db, principal, group_id)
    if len(g.files) < 2:
        return [_group_out(db, g)]
    out = [g]
    for f in list(g.files[1:]):
        new = UploadGroup(owner_id=g.owner_id, batch_id=g.batch_id, pairing_rule="manual", label=f.original_filename)
        g.files.remove(f)
        f.seq = 0
        new.files.append(f)
        db.add(new)
        out.append(new)
    g.pairing_rule = "manual"
    db.commit()
    return [_group_out(db, x) for x in out]


@router.post("/groups/merge", response_model=UploadGroupOut)
def merge_groups(body: GroupMerge, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    groups = [_group(db, principal, gid) for gid in dict.fromkeys(body.group_ids)]
    if len(groups) < 2:
        raise HTTPException(422, "Pick at least two different groups")
    target = groups[0]
    seq = len(target.files)
    for other in groups[1:]:
        for f in list(other.files):
            other.files.remove(f)
            f.seq = seq
            seq += 1
            target.files.append(f)
        db.delete(other)
    target.pairing_rule = "manual"
    db.commit()
    return _group_out(db, target)


def _attach_files(db: Session, principal: Principal, g: UploadGroup, item) -> None:
    order = media.next_sort_order(db, item.id)
    for i, f in enumerate(g.files):
        stored = StoredImage(
            storage_key=f.storage_key,
            sha256=f.sha256,
            mime=f.mime,
            width=f.width,
            height=f.height,
            bytes=f.bytes,
            phash=f.phash or "",
            quality=f.quality or {},
        )
        media.add_photo(db, item, stored, f.suggested_role, f.original_filename, order + i)
    media.ensure_cover(db, item)
    g.resulting_item_id = item.id
    g.resolved_at = utcnow()


@router.post("/groups/{group_id}/attach", response_model=ItemOut)
def attach_group(group_id: int, body: GroupAttach, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    g = _group(db, principal, group_id)
    item = item_svc.get_item(db, principal, body.item_id)
    _attach_files(db, principal, g, item)
    g.status = "attached"
    db.commit()
    return item_svc.item_out(db, item)


@router.post("/groups/{group_id}/create-item", response_model=ItemOut, status_code=201)
def create_item_from_group(
    group_id: int, body: GroupCreateItem, principal: Principal = Depends(write_items), db: Session = Depends(get_db)
):
    g = _group(db, principal, group_id)
    item = item_svc.create_item(db, principal, body.item)
    _attach_files(db, principal, g, item)
    g.status = "created_item"
    db.commit()
    return item_svc.item_out(db, item)


@router.post("/groups/{group_id}/discard", response_model=UploadGroupOut)
def discard_group(group_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Hide a group. Its original files stay on disk so nothing you photographed is lost."""
    g = _group(db, principal, group_id)
    g.status = "discarded"
    g.resolved_at = utcnow()
    db.commit()
    return _group_out(db, g)
