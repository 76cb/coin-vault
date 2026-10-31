"""Photos on items, and authenticated serving of photo and upload files."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Item, Photo
from app.models import UploadFile as UploadFileRow
from app.schemas import CoverIn, PhotoEditsIn, PhotoOrder, PhotoOut, PhotoPatch, PhotoRole
from app.services import items as item_svc
from app.services import media, photo_edit, storage
from app.services.images import IntakeError, store_image

router = APIRouter(tags=["photos"])

Size = Literal["thumb", "medium", "original"]
PhotoSize = Literal["thumb", "medium", "original", "unedited", "edited"]


def _photo(db: Session, principal: Principal, photo_id: int) -> Photo:
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    item = db.get(Item, photo.item_id)
    if item is None or item.owner_id != principal.owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return photo


class PhotoUploadResult(PhotoOut):
    duplicate_of_photo_id: int | None = None
    duplicate_of_item_id: int | None = None
    duplicate_kind: str | None = None


@router.post("/items/{item_id}/photos", response_model=list[PhotoUploadResult], status_code=201)
async def upload_photos(
    item_id: int,
    files: Annotated[list[UploadFile], File(description="One or more image files")],
    roles: Annotated[list[PhotoRole] | None, Form(description="Optional role per file, in the same order")] = None,
    principal: Principal = Depends(write_items),
    db: Session = Depends(get_db),
):
    s = get_settings()
    item = item_svc.get_item(db, principal, item_id)
    if len(files) > s.max_files_per_upload:
        raise HTTPException(413, f"At most {s.max_files_per_upload} files at once")
    roles = roles or []
    results: list[PhotoUploadResult] = []
    order = media.next_sort_order(db, item.id)
    max_bytes = s.max_photo_mb * 1024 * 1024
    for idx, up in enumerate(files):
        data = await media.read_limited(up, max_bytes)
        try:
            stored = store_image(data, max_bytes)
        except IntakeError as exc:
            raise HTTPException(422, f"{up.filename}: {exc}") from exc
        dup = media.find_duplicate(db, principal.owner_id, stored)
        role = roles[idx] if idx < len(roles) else ("obverse" if not item.photos and idx == 0 else "other")
        photo = media.add_photo(db, item, stored, role, up.filename, order + idx)
        out = item_svc.photo_out(photo).model_dump()
        results.append(
            PhotoUploadResult(
                **out,
                duplicate_of_photo_id=dup[0] if dup else None,
                duplicate_of_item_id=dup[1] if dup else None,
                duplicate_kind=dup[2] if dup else None,
            )
        )
    media.ensure_cover(db, item)
    db.commit()
    return results


@router.patch("/photos/{photo_id}", response_model=PhotoOut)
def patch_photo(photo_id: int, body: PhotoPatch, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    photo = _photo(db, principal, photo_id)
    photo.role = body.role
    db.commit()
    return item_svc.photo_out(photo)


def _drop_edited(db: Session, photo: Photo) -> None:
    """Delete the photo's edited copies unless another photo shows the same file with the same edits."""
    if not photo.edits:
        return
    ehash = photo_edit.edit_hash(photo.edits)
    others = db.scalars(select(Photo).where(Photo.sha256 == photo.sha256, Photo.id != photo.id, Photo.edits.is_not(None)))
    if not any(photo_edit.edit_hash(o.edits) == ehash for o in others):
        photo_edit.remove_edited(photo.sha256, ehash)


@router.put("/photos/{photo_id}/edits", response_model=PhotoOut)
def set_edits(photo_id: int, body: PhotoEditsIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Save crop, straighten and colour settings; the display copies are rendered from the untouched original."""
    photo = _photo(db, principal, photo_id)
    edits = body.edits.model_dump(exclude_defaults=True) if body.edits and not body.edits.is_identity() else None
    if edits == photo.edits:
        return item_svc.photo_out(photo)
    if edits:
        try:
            _, width, height = photo_edit.write_edited(photo.storage_key, photo.sha256, edits)
        except (OSError, ValueError) as exc:
            raise HTTPException(422, f"The photo couldn't be edited: {exc}") from exc
    else:
        width, height = photo_edit.display_size(photo.storage_key)
    _drop_edited(db, photo)
    photo.edits = edits
    photo.width, photo.height = width, height
    db.commit()
    return item_svc.photo_out(photo)


@router.put("/items/{item_id}/photos/order", response_model=list[PhotoOut])
def reorder_photos(
    item_id: int, body: PhotoOrder, principal: Principal = Depends(write_items), db: Session = Depends(get_db)
):
    item = item_svc.get_item(db, principal, item_id)
    ids = [p.id for p in item.photos]
    if sorted(ids) != sorted(body.photo_ids):
        raise HTTPException(422, "Send every photo id of this item exactly once")
    by_id = {p.id: p for p in item.photos}
    for pos, pid in enumerate(body.photo_ids, start=1):
        by_id[pid].sort_order = pos
    db.commit()
    db.refresh(item, ["photos"])
    return [item_svc.photo_out(p) for p in item.photos]


@router.put("/items/{item_id}/cover", status_code=204)
def set_cover(item_id: int, body: CoverIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    item = item_svc.get_item(db, principal, item_id)
    if body.photo_id not in {p.id for p in item.photos}:
        raise HTTPException(422, "That photo belongs to another item")
    item.cover_photo_id = body.photo_id
    db.commit()


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    photo = _photo(db, principal, photo_id)
    item = db.get(Item, photo.item_id)
    key, sha = photo.storage_key, photo.sha256
    _drop_edited(db, photo)
    if item.cover_photo_id == photo.id:
        item.cover_photo_id = None
    db.delete(photo)
    db.flush()
    media.ensure_cover(db, item)
    media.release_file(db, key, sha)
    db.commit()


def _serve(storage_key: str, sha256: str, mime: str, size: Size, filename: str | None) -> Response:
    if size == "original":
        key, media_type = storage_key, mime
    else:
        key, media_type = storage.derived_key(sha256, size), "image/webp"
    return _serve_key(key, media_type, filename if size == "original" else None)


def _serve_key(key: str, media_type: str, filename: str | None = None) -> Response:
    path = storage.path_for(key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing on disk")
    headers = {"Cache-Control": "private, max-age=86400, immutable", "X-Content-Type-Options": "nosniff"}
    s = get_settings()
    if s.use_x_accel:
        headers["X-Accel-Redirect"] = f"{s.x_accel_prefix}/{key}"
        return Response(status_code=200, media_type=media_type, headers=headers)
    return FileResponse(
        path, media_type=media_type, headers=headers, filename=filename or None, content_disposition_type="inline"
    )


@router.get("/media/photos/{photo_id}/{size}")
def serve_photo(photo_id: int, size: PhotoSize, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    """thumb and medium show the edits; original is the file as uploaded; unedited is medium without
    edits (what the editor starts from); edited is the edited photo at full size, as a JPEG."""
    photo = _photo(db, principal, photo_id)
    if size == "unedited":
        return _serve(photo.storage_key, photo.sha256, photo.mime, "medium", None)
    if size == "edited":
        if not photo.edits:
            return _serve(photo.storage_key, photo.sha256, photo.mime, "original", photo.original_filename)
        stem = (photo.original_filename or f"photo-{photo.id}").rsplit(".", 1)[0]
        return Response(photo_edit.full_jpeg(photo.storage_key, photo.edits), media_type="image/jpeg", headers={
            "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{stem}-edited.jpg"'})
    if photo.edits and size in ("thumb", "medium"):
        key = photo_edit.edited_key(photo.sha256, size, photo_edit.edit_hash(photo.edits))
        if not storage.exists(key):  # e.g. derived files cleared; render them again
            photo_edit.write_edited(photo.storage_key, photo.sha256, photo.edits)
        return _serve_key(key, "image/webp")
    return _serve(photo.storage_key, photo.sha256, photo.mime, size, photo.original_filename)


@router.get("/media/uploads/{file_id}/{size}")
def serve_upload_file(
    file_id: int, size: Size, principal: Principal = Depends(read_items), db: Session = Depends(get_db)
):
    row = db.scalar(
        select(UploadFileRow).where(UploadFileRow.id == file_id, UploadFileRow.owner_id == principal.owner_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return _serve(row.storage_key, row.sha256, row.mime, size, row.original_filename)
