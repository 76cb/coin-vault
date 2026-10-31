"""Photo library: every image the owner has uploaded, whether on items or waiting in bulk uploads, and putting
one on an item without uploading it again (the file is shared, not copied)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Item, Photo, UploadGroup
from app.models import UploadFile as UploadFileRow
from app.routers.photos import _drop_edited, _serve
from app.schemas import PhotoOut, PhotoRole, _Base
from app.services import items as item_svc
from app.services import media, photo_edit
from app.services.images import StoredImage

router = APIRouter(tags=["photos"])


class LibraryUse(BaseModel):
    item_id: int
    title: str
    photo_id: int
    role: str
    is_cover: bool


class LibraryFile(BaseModel):
    sha256: str
    urls: dict[str, str]
    width: int
    height: int
    bytes: int
    filename: str | None
    created_at: dt.datetime
    items: list[LibraryUse]
    waiting_upload: bool  # in a bulk upload that hasn't been filed yet


class LibraryOut(BaseModel):
    total: int
    files: list[LibraryFile]


def _urls(sha: str) -> dict[str, str]:
    base = f"/api/v1/media/library/{sha}"
    return {"thumb": f"{base}/thumb", "medium": f"{base}/medium", "original": f"{base}/original"}


def _owned(db: Session, owner_id: int, sha: str) -> tuple[Photo | None, UploadFileRow | None]:
    photo = db.scalar(
        select(Photo).join(Item, Item.id == Photo.item_id)
        .where(Item.owner_id == owner_id, Photo.sha256 == sha).order_by(Photo.id).limit(1)
    )
    upload = db.scalar(
        select(UploadFileRow).where(UploadFileRow.owner_id == owner_id, UploadFileRow.sha256 == sha)
        .order_by(UploadFileRow.id).limit(1)
    )
    return photo, upload


@router.get("/library", response_model=LibraryOut)
def library(
    show: Literal["all", "on_items", "not_on_items"] = "all",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=60, ge=1, le=200),
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
):
    """Each image once, newest first, with the items it's on."""
    files: dict[str, dict] = {}
    rows = db.execute(
        select(Photo, Item.id, Item.title, Item.cover_photo_id).join(Item, Item.id == Photo.item_id)
        .where(Item.owner_id == principal.owner_id, Item.deleted_at.is_(None))
    )
    for p, item_id, title, cover in rows:
        f = files.setdefault(p.sha256, {
            "sha256": p.sha256, "urls": _urls(p.sha256), "width": p.width, "height": p.height, "bytes": p.bytes,
            "filename": p.original_filename, "created_at": p.created_at, "items": [], "waiting_upload": False,
            "_edited": bool(p.edits),
        })
        if p.edits and not f.get("_plain_size"):
            f["width"], f["height"] = photo_edit.display_size(p.storage_key)
            f["_plain_size"] = True
        f["created_at"] = min(f["created_at"], p.created_at)
        f["items"].append(LibraryUse(item_id=item_id, title=title, photo_id=p.id, role=p.role, is_cover=cover == p.id))
    ups = db.execute(
        select(UploadFileRow, UploadGroup.status).join(UploadGroup, UploadGroup.id == UploadFileRow.group_id)
        .where(UploadFileRow.owner_id == principal.owner_id)
    )
    for u, status in ups:
        f = files.setdefault(u.sha256, {
            "sha256": u.sha256, "urls": _urls(u.sha256), "width": u.width, "height": u.height, "bytes": u.bytes,
            "filename": u.original_filename, "created_at": u.created_at, "items": [], "waiting_upload": False,
        })
        f["created_at"] = min(f["created_at"], u.created_at)
        f["filename"] = f["filename"] or u.original_filename
        if status == "pending":
            f["waiting_upload"] = True
    out = [LibraryFile(**{k: v for k, v in f.items() if not k.startswith("_")}) for f in files.values()]
    if show == "on_items":
        out = [f for f in out if f.items]
    elif show == "not_on_items":
        out = [f for f in out if not f.items]
    out.sort(key=lambda f: (f.created_at if f.created_at.tzinfo else f.created_at.replace(tzinfo=dt.UTC)), reverse=True)
    start = (page - 1) * per_page
    return LibraryOut(total=len(out), files=out[start : start + per_page])


@router.get("/media/library/{sha256}/{size}")
def serve_library_file(
    sha256: str, size: Literal["thumb", "medium", "original"], principal: Principal = Depends(read_items), db: Session = Depends(get_db)
):
    """The file as uploaded (no edits): any image of yours, by its content hash."""
    if len(sha256) != 64 or not all(c in "0123456789abcdef" for c in sha256):
        raise HTTPException(404, "Not found")
    photo, upload = _owned(db, principal.owner_id, sha256)
    src = photo or upload
    if src is None:
        raise HTTPException(404, "Not found")
    return _serve(src.storage_key, src.sha256, src.mime, size, src.original_filename)


class FromLibraryIn(_Base):
    sha256: str
    role: PhotoRole = "other"
    make_cover: bool = False


@router.post("/items/{item_id}/photos/from-library", response_model=PhotoOut, status_code=201)
def add_from_library(item_id: int, body: FromLibraryIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Put an image you already uploaded on this item. Nothing is uploaded or copied; the file is shared."""
    item = item_svc.get_item(db, principal, item_id)
    if any(p.sha256 == body.sha256 for p in item.photos):
        raise HTTPException(409, "That photo is already on this item")
    photo, upload = _owned(db, principal.owner_id, body.sha256)
    src = photo or upload
    if src is None:
        raise HTTPException(404, "That photo isn't in your library")
    width, height = photo_edit.display_size(src.storage_key) if photo is not None and photo.edits else (src.width, src.height)
    stored = StoredImage(
        storage_key=src.storage_key, sha256=src.sha256, mime=src.mime, width=width, height=height, bytes=src.bytes,
        phash=src.phash, quality=dict(src.quality or {}),  # type: ignore[arg-type]
    )
    new = media.add_photo(db, item, stored, body.role, src.original_filename, media.next_sort_order(db, item.id))
    if body.make_cover:
        item.cover_photo_id = new.id
    else:
        media.ensure_cover(db, item)
    db.commit()
    return item_svc.photo_out(new)


class DeleteIn(_Base):
    sha256s: list[str] = Field(min_length=1, max_length=500)


class DeleteOut(BaseModel):
    deleted: int  # files removed
    photos_removed: int  # photos taken off items
    uploads_removed: int  # files taken out of bulk uploads


@router.post("/library/delete", response_model=DeleteOut)
def delete_files(body: DeleteIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Delete photos everywhere: off every item they're on and out of any bulk upload, then the files themselves
    (a file is only removed from disk when nothing of anyone's still uses it)."""
    wanted = set(body.sha256s)
    photos = list(db.scalars(
        select(Photo).join(Item, Item.id == Photo.item_id).where(Item.owner_id == principal.owner_id, Photo.sha256.in_(wanted))
    ))
    uploads = list(db.scalars(
        select(UploadFileRow).where(UploadFileRow.owner_id == principal.owner_id, UploadFileRow.sha256.in_(wanted))
    ))
    found = {p.sha256 for p in photos} | {u.sha256 for u in uploads}
    if not found:
        raise HTTPException(404, "None of those photos are in your library")
    files = {(p.storage_key, p.sha256) for p in photos} | {(u.storage_key, u.sha256) for u in uploads}
    touched_items = {p.item_id for p in photos}
    groups = {u.group_id for u in uploads}
    for p in photos:
        _drop_edited(db, p)
        item = db.get(Item, p.item_id)
        if item is not None and item.cover_photo_id == p.id:
            item.cover_photo_id = None
        db.delete(p)
    for u in uploads:
        db.delete(u)
    db.flush()
    for item_id in touched_items:
        item = db.get(Item, item_id)
        if item is not None:
            media.ensure_cover(db, item)
    for gid in groups:  # a bulk-upload group left with nothing in it is done with
        g = db.get(UploadGroup, gid)
        if g is not None:
            db.refresh(g, ["files"])
            if not g.files and g.status == "pending":
                g.status = "discarded"
    for key, sha in files:
        media.release_file(db, key, sha)
    db.commit()
    return DeleteOut(deleted=len(found), photos_removed=len(photos), uploads_removed=len(uploads))
