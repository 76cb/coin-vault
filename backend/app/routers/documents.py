"""Receipts, invoices, certificates and assay cards. Served only to the signed-in owner."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Document, Item, document_links
from app.schemas import DocKind, DocumentLinks, DocumentOut, DocumentPatch
from app.services import items as item_svc
from app.services import media, storage
from app.services.images import IntakeError, store_document

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc(db: Session, principal: Principal, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.owner_id != principal.owner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


def _owned_items(db: Session, principal: Principal, item_ids: list[int]) -> list[Item]:
    if not item_ids:
        return []
    found = db.scalars(
        select(Item).where(Item.id.in_(item_ids), Item.owner_id == principal.owner_id, Item.deleted_at.is_(None))
    ).all()
    if len(found) != len(set(item_ids)):
        raise HTTPException(422, "One or more items do not exist")
    return list(found)


def _out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        kind=doc.kind,
        title=doc.title,
        doc_date=doc.doc_date,
        mime=doc.mime,
        bytes=doc.bytes,
        original_filename=doc.original_filename,
        created_at=doc.created_at,
        item_ids=[i.id for i in doc.items],
        url=item_svc.document_url(doc.id),
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    item_id: int | None = Query(default=None),
    principal: Principal = Depends(read_items),
    db: Session = Depends(get_db),
):
    stmt = select(Document).where(Document.owner_id == principal.owner_id).order_by(Document.created_at.desc())
    if item_id is not None:
        stmt = stmt.join(document_links, document_links.c.document_id == Document.id).where(
            document_links.c.item_id == item_id
        )
    return [_out(d) for d in db.scalars(stmt).unique()]


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
    kind: Annotated[DocKind, Form()] = "other",
    doc_date: Annotated[dt.date | None, Form()] = None,
    item_ids: Annotated[list[int] | None, Form()] = None,
    principal: Principal = Depends(write_items),
    db: Session = Depends(get_db),
):
    max_bytes = get_settings().max_document_mb * 1024 * 1024
    data = await media.read_limited(file, max_bytes)
    try:
        stored = store_document(data, max_bytes)
    except IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc
    items = _owned_items(db, principal, item_ids or [])
    doc = Document(
        owner_id=principal.owner_id,
        kind=kind,
        title=(title or file.filename or "Document").strip()[:200],
        doc_date=doc_date,
        storage_key=stored.storage_key,
        sha256=stored.sha256,
        mime=stored.mime,
        bytes=stored.bytes,
        original_filename=file.filename,
    )
    doc.items = items
    db.add(doc)
    db.commit()
    return _out(doc)


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    return _out(_doc(db, principal, doc_id))


@router.get("/{doc_id}/file")
def document_file(doc_id: int, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    doc = _doc(db, principal, doc_id)
    path = storage.path_for(doc.storage_key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing on disk")
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    s = get_settings()
    if s.use_x_accel:
        headers["X-Accel-Redirect"] = f"{s.x_accel_prefix}/{doc.storage_key}"
        return Response(status_code=200, media_type=doc.mime, headers=headers)
    return FileResponse(
        path, media_type=doc.mime, headers=headers, filename=doc.original_filename, content_disposition_type="inline"
    )


@router.patch("/{doc_id}", response_model=DocumentOut)
def patch_document(doc_id: int, body: DocumentPatch, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    doc = _doc(db, principal, doc_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k in ("kind", "title") and v is None:
            continue
        setattr(doc, k, v)
    db.commit()
    return _out(doc)


@router.put("/{doc_id}/links", response_model=DocumentOut)
def set_links(doc_id: int, body: DocumentLinks, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    doc = _doc(db, principal, doc_id)
    doc.items = _owned_items(db, principal, body.item_ids)
    db.commit()
    return _out(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    doc = _doc(db, principal, doc_id)
    key = doc.storage_key
    db.delete(doc)
    media.release_document_file(db, key)
    db.commit()
