"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings
from app.db import get_engine
from app.deps import request_id_var
from app.logging_setup import log, setup_logging
from app.migrate import upgrade_to_head
from app import scheduler
from app.routers import auth, compositions, documents, health, items, photos, prices, reference, settings, uploads
from app.services import storage

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    storage.ensure_dirs()
    if s.run_migrations_on_startup:
        upgrade_to_head(get_engine())
        log.info("migrations_applied")
    scheduler.start()
    log.info("startup", version=__version__, media_root=str(storage.media_root()))
    yield
    scheduler.stop()


def create_app() -> FastAPI:
    s = get_settings()
    setup_logging(s.log_level, s.log_json)
    app = FastAPI(
        title="Coin Vault",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        redoc_url=None,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        rid = rid[:36]
        token = request_id_var.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled_error", path=request.url.path, method=request.method)
            response = JSONResponse({"detail": "Internal error", "request_id": rid}, status_code=500)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=round((time.perf_counter() - start) * 1000, 1),
            )
        structlog.contextvars.unbind_contextvars("request_id")
        return response

    for r in (
        health.router, auth.router, items.router, reference.router, photos.router, documents.router, uploads.router,
        prices.router, compositions.router, settings.router,
    ):
        app.include_router(r, prefix=API_PREFIX)

    dist = s.frontend_dist
    if dist and Path(dist).is_dir():
        dist = Path(dist)
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
