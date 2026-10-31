"""Settings, Value updates: the weekly refresh of PCGS price guide values and Numista estimates."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import scheduler
from app.db import get_db, session_factory
from app.deps import Principal
from app.models import Item
from app.routers.backups import require_admin
from app.services import value_updates
from app.services.providers import get_system, set_system

router = APIRouter(prefix="/value-updates", tags=["value updates"])

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class UpdatesOut(BaseModel):
    enabled: bool
    day: str
    time: str
    timezone: str
    next_run: dt.datetime | None
    running: bool
    tracked_pcgs: int  # items with a PCGS price guide value (these are updated)
    tracked_numista: int
    last: dict | None


class UpdatesSettingsIn(BaseModel):
    enabled: bool
    day: Day
    time: str

    @field_validator("time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v.strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("Use a 24-hour time like 05:40")
        return f"{int(m.group(1)):02d}:{m.group(2)}"


def _tracked(db: Session) -> tuple[int, int]:
    pcgs = numista = 0
    for it in db.scalars(select(Item).where(Item.deleted_at.is_(None), Item.status != "sold").options(selectinload(Item.valuations))):
        sources = {value_updates._source_of(v) for v in it.valuations}
        pcgs += "pcgs" in sources
        numista += "numista" in sources
    return pcgs, numista


@router.get("", response_model=UpdatesOut)
def status(principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    from app.config import get_settings

    pcgs, numista = _tracked(db)
    last = get_system(db, "updates_last")
    enabled = bool(get_system(db, "updates_enabled"))
    return UpdatesOut(
        enabled=enabled, day=str(get_system(db, "updates_day")), time=str(get_system(db, "updates_time")),
        timezone=get_settings().timezone, next_run=scheduler.next_updates_run() if enabled else None,
        running=value_updates.is_running(db), tracked_pcgs=pcgs, tracked_numista=numista,
        last=last if isinstance(last, dict) else None,
    )


@router.put("/settings", response_model=UpdatesOut)
def save_settings(body: UpdatesSettingsIn, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    set_system(db, "updates_enabled", body.enabled)
    set_system(db, "updates_day", body.day)
    set_system(db, "updates_time", body.time)
    db.commit()
    scheduler.reschedule_updates(body.day, body.time)
    return status(principal, db)


def _run_in_background() -> None:
    with session_factory()() as db:
        try:
            value_updates.run_and_record(db)
        except Exception:  # recorded for Settings
            pass


@router.post("", response_model=UpdatesOut, status_code=202)
def run_now(background: BackgroundTasks, principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    """Start an update now; it runs after this reply (it can take a while), and Settings shows how it went."""
    if value_updates.is_running(db):
        raise HTTPException(409, "An update is already running")
    background.add_task(_run_in_background)
    out = status(principal, db)
    out.running = True
    return out
