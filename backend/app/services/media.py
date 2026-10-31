"""Shared photo helpers: reading uploads safely, duplicate detection, attaching and file cleanup."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, Item, Photo, UploadFile as UploadFileRow
from app.services import storage
from app.services.images import StoredImage, phash_distance

CHUNK = 1024 * 1024


async def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, refusing anything larger than max_bytes without buffering it all."""
    buf = bytearray()
    while True:
        chunk = await upload.read(CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                413,
                f"{upload.filename or 'file'} is larger than {max_bytes // CHUNK} MB",
            )
    return bytes(buf)


def find_duplicate(db: Session, owner_id: int, stored: StoredImage) -> tuple[int, int, str] | None:
    """Return (photo_id, item_id, 'exact'|'similar') for the closest existing photo, if any."""
    base = (
        select(Photo.id, Photo.item_id, Photo.sha256, Photo.phash)
        .join(Item, Item.id == Photo.item_id)
        .where(Item.owner_id == owner_id, Item.deleted_at.is_(None))
    )
    exact = db.execute(base.where(Photo.sha256 == stored.sha256).limit(1)).first()
    if exact:
        return exact.id, exact.item_id, "exact"
    limit = get_settings().phash_duplicate_distance
    best: tuple[int, int, int] | None = None
    for row in db.execute(base):
        d = phash_distance(stored.phash, row.phash)
        if d is not None and d <= limit and (best is None or d < best[2]):
            best = (row.id, row.item_id, d)
    if best:
        return best[0], best[1], "similar"
    return None


def next_sort_order(db: Session, item_id: int) -> int:
    current = db.scalar(select(func.max(Photo.sort_order)).where(Photo.item_id == item_id))
    return (current or 0) + 1


def add_photo(
    db: Session, item: Item, stored: StoredImage, role: str, original_filename: str | None, sort_order: int
) -> Photo:
    photo = Photo(
        item_id=item.id,
        role=role,
        sort_order=sort_order,
        storage_key=stored.storage_key,
        sha256=stored.sha256,
        phash=stored.phash,
        mime=stored.mime,
        width=stored.width,
        height=stored.height,
        bytes=stored.bytes,
        quality=stored.quality,
        original_filename=original_filename,
    )
    db.add(photo)
    db.flush()
    return photo


def ensure_cover(db: Session, item: Item) -> None:
    db.flush()
    db.refresh(item, ["photos"])
    if item.cover_photo_id and any(p.id == item.cover_photo_id for p in item.photos):
        return
    obverse = next((p for p in item.photos if p.role == "obverse"), None)
    first = obverse or (item.photos[0] if item.photos else None)
    item.cover_photo_id = first.id if first else None


def release_file(db: Session, storage_key: str, sha256: str) -> None:
    """Delete a stored image and its derivatives once nothing references it."""
    db.flush()
    refs = (db.scalar(select(func.count()).select_from(Photo).where(Photo.storage_key == storage_key)) or 0) + (
        db.scalar(select(func.count()).select_from(UploadFileRow).where(UploadFileRow.storage_key == storage_key)) or 0
    )
    if refs:
        return
    storage.remove(storage_key)
    for size in storage.DERIVED_SIZES:
        storage.remove(storage.derived_key(sha256, size))
    storage.remove_matching(storage.derived_key(sha256, "x").rsplit("/", 1)[0], f"{sha256}_*_e*.*")  # edited copies: thumb, medium and full size


def release_document_file(db: Session, storage_key: str) -> None:
    db.flush()
    refs = db.scalar(select(func.count()).select_from(Document).where(Document.storage_key == storage_key)) or 0
    if not refs:
        storage.remove(storage_key)
