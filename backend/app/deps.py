"""Request dependencies: authentication, CSRF and scope checks."""

from __future__ import annotations

import contextvars
import datetime as dt
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import ApiToken, User, UserSession, utcnow
from app.security import SCOPES, constant_time_equals, parse_api_token, sha256_hex

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-CSRF-Token"


@dataclass
class Principal:
    user: User
    kind: str  # "session" or "token"
    scopes: set[str] = field(default_factory=set)
    session: UserSession | None = None
    token: ApiToken | None = None

    @property
    def owner_id(self) -> int:
        return self.user.id

    @property
    def actor(self) -> tuple[str, int]:
        if self.kind == "token" and self.token is not None:
            return ("token", self.token.id)
        return ("user", self.user.id)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is not None and value.tzinfo is None:  # SQLite returns naive datetimes
        return value.replace(tzinfo=dt.UTC)
    return value


def _from_token(raw: str, db: Session) -> Principal | None:
    prefix = parse_api_token(raw)
    if prefix is None:
        return None
    token = db.scalar(select(ApiToken).where(ApiToken.prefix == prefix))
    if token is None or not constant_time_equals(token.token_hash, sha256_hex(raw)):
        return None
    now = utcnow()
    if token.revoked_at is not None:
        return None
    expires = _aware(token.expires_at)
    if expires is not None and expires <= now:
        return None
    if not token.user.is_active:
        return None
    last = _aware(token.last_used_at)
    if last is None or now - last > dt.timedelta(minutes=5):
        token.last_used_at = now
        db.commit()
    return Principal(user=token.user, kind="token", scopes=set(token.scopes or []), token=token)


def _from_session(raw: str, db: Session) -> Principal | None:
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == sha256_hex(raw)))
    if sess is None:
        return None
    now = utcnow()
    if _aware(sess.expires_at) <= now or not sess.user.is_active:
        db.delete(sess)
        db.commit()
        return None
    if now - _aware(sess.last_seen_at) > dt.timedelta(minutes=5):
        sess.last_seen_at = now
        db.commit()
    return Principal(user=sess.user, kind="session", scopes=set(SCOPES), session=sess)


def optional_principal(request: Request, db: Session = Depends(get_db)) -> Principal | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        principal = _from_token(auth[7:].strip(), db)
        if principal is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired API token")
        return principal
    raw = request.cookies.get(get_settings().session_cookie_name)
    if not raw:
        return None
    principal = _from_session(raw, db)
    if principal is None:
        return None
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not constant_time_equals(sent, principal.session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    return principal


def current_principal(principal: Principal | None = Depends(optional_principal)) -> Principal:
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return principal


def require_scope(scope: str):
    assert scope in SCOPES, scope

    def checker(principal: Principal = Depends(current_principal)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Token lacks scope {scope}")
        return principal

    return checker


def require_session(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.kind != "session":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action needs a signed-in browser session")
    return principal


read_items = require_scope("items:read")
write_items = require_scope("items:write")
