"""Liveness (public) and readiness (signed in) checks."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_db, get_engine
from app.deps import Principal, current_principal
from app.migrate import current_and_head
from app.services import storage

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response, _: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    checks: dict[str, dict] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:  # pragma: no cover - depends on a broken DB
        checks["database"] = {"ok": False, "error": type(exc).__name__}
    try:
        current, head = current_and_head(get_engine())
        checks["migrations"] = {"ok": current == head, "current": current, "head": head}
    except Exception as exc:  # pragma: no cover
        checks["migrations"] = {"ok": False, "error": type(exc).__name__}
    from app import scheduler
    from app.config import get_settings

    checks["scheduler"] = {"ok": scheduler.running() or not get_settings().scheduler_enabled, "running": scheduler.running()}
    root = storage.media_root()
    checks["media"] = {"ok": root.is_dir() and os.access(root, os.W_OK)}
    ok = all(c["ok"] for c in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "degraded", "version": __version__, "checks": checks}
