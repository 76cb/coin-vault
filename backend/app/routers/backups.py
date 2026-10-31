"""Backups in Settings: status, make one now, the schedule, delete, and download one as a single .tar.

Backups hold everyone's data, so only an admin, signed in with a browser session, can manage them.
"""

from __future__ import annotations

import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import scheduler
from app.db import get_db
from app.deps import Principal, require_session
from app.services import backup
from app.services.providers import get_system, set_system

router = APIRouter(prefix="/backups", tags=["backups"])


def require_admin(principal: Principal = Depends(require_session)) -> Principal:
    if not principal.user.is_admin:
        raise HTTPException(403, "Only an admin can manage backups")
    return principal


class BackupOut(BaseModel):
    name: str
    created_at: dt.datetime
    reason: str
    counts: dict
    files: int
    database_bytes: int
    media_bytes: int
    new_files: int
    verified: bool
    seconds: float | None
    download_bytes: int


class LastRun(BaseModel):
    at: dt.datetime | None = None
    ok: bool | None = None
    name: str | None = None
    error: str | None = None


class BackupsOut(BaseModel):
    enabled: bool
    time: str
    timezone: str
    folder: str
    free_bytes: int | None
    next_run: dt.datetime | None
    last: LastRun | None
    backups: list[BackupOut]


class BackupSettingsIn(BaseModel):
    enabled: bool
    time: str

    @field_validator("time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v.strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("Use a 24-hour time like 03:15")
        return f"{int(m.group(1)):02d}:{m.group(2)}"


def _out(b: backup.BackupInfo) -> BackupOut:
    m = b.manifest
    return BackupOut(
        name=b.name, created_at=b.created_at, reason=m.get("reason", "manual"), counts=m.get("counts", {}),
        files=len(m.get("files", [])), database_bytes=m["database"]["size"], media_bytes=m.get("media_bytes", 0),
        new_files=m.get("new_files", 0), verified=bool(m.get("verified")), seconds=m.get("seconds"),
        download_bytes=backup.archive_size(b),
    )


@router.get("", response_model=BackupsOut)
def status(principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    from app.config import get_settings

    last = get_system(db, "backup_last")
    return BackupsOut(
        enabled=bool(get_system(db, "backup_enabled")),
        time=str(get_system(db, "backup_time")),
        timezone=get_settings().timezone,
        folder=str(backup.backup_root()),
        free_bytes=backup.disk_free(),
        next_run=scheduler.next_backup_run() if get_system(db, "backup_enabled") else None,
        last=LastRun(**last) if isinstance(last, dict) else None,
        backups=[_out(b) for b in backup.list_backups()],
    )


@router.post("", response_model=BackupOut, status_code=201)
def make_now(principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    """Back up now. The first backup copies every file; later ones only copy what's new."""
    try:
        b = backup.run_backup(db, reason="manual")
    except backup.BackupError as exc:
        set_system(db, "backup_last", {"at": dt.datetime.now(dt.UTC).isoformat(), "ok": False, "name": None, "error": str(exc)})
        db.commit()
        raise HTTPException(500, f"The backup failed: {exc}") from exc
    set_system(db, "backup_last", {"at": b.manifest["created_at"], "ok": True, "name": b.name, "error": None})
    db.commit()
    return _out(b)


@router.put("/settings", response_model=BackupsOut)
def save_settings(body: BackupSettingsIn, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    set_system(db, "backup_enabled", body.enabled)
    set_system(db, "backup_time", body.time)
    db.commit()
    scheduler.reschedule_backup(body.time)
    return status(principal, db)


@router.delete("/{name}", status_code=204)
def delete(name: str, principal: Principal = Depends(require_admin)):
    try:
        backup.delete_backup(name)
    except backup.BackupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{name}/download")
def download(name: str, principal: Principal = Depends(require_admin)):
    """The whole backup as one .tar (database and every file), to keep somewhere else or restore from."""
    try:
        b = backup.get_backup(name)
    except backup.BackupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return StreamingResponse(
        backup.archive_stream(b),
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="coinvault-backup-{b.name}.tar"', "Cache-Control": "no-store"},
    )
