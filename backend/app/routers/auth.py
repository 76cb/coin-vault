"""Login, logout, password change and scoped API tokens."""

from __future__ import annotations

import datetime as dt
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import Principal, current_principal, require_session
from app.logging_setup import log
from app.models import ApiToken, User, UserSession, utcnow
from app.security import (
    DUMMY_HASH,
    MIN_PASSWORD_LENGTH,
    SCOPES,
    hash_password,
    needs_rehash,
    new_api_token,
    new_csrf_token,
    new_session_token,
    sha256_hex,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class _Throttle:
    """In-memory failed-login limiter per client IP (single-process app)."""

    def __init__(self) -> None:
        self._fails: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        s = get_settings()
        with self._lock:
            q = self._fails[key]
            cutoff = time.monotonic() - s.login_window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            return len(q) >= s.login_max_failures

    def fail(self, key: str) -> None:
        with self._lock:
            self._fails[key].append(time.monotonic())

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._fails.clear()
            else:
                self._fails.pop(key, None)


throttle = _Throttle()


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool
    base_currency: str


class MeOut(BaseModel):
    user: UserOut
    auth: str
    csrf_token: str | None = None
    scopes: list[str]


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=1024)

    @field_validator("new_password")
    @classmethod
    def _long_enough(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"must be at least {MIN_PASSWORD_LENGTH} characters")
        return v


class TokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("scopes")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        bad = sorted(set(v) - set(SCOPES))
        if bad:
            raise ValueError(f"unknown scopes: {', '.join(bad)}; allowed: {', '.join(SCOPES)}")
        return sorted(set(v))


class TokenOut(BaseModel):
    id: int
    name: str
    prefix: str
    scopes: list[str]
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    expires_at: dt.datetime | None
    revoked_at: dt.datetime | None


class TokenCreatedOut(TokenOut):
    token: str


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, is_admin=u.is_admin, base_currency=u.base_currency)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    ip = _client_ip(request)
    if throttle.blocked(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed logins; wait a few minutes")
    user = db.scalar(select(User).where(User.username == body.username))
    ok = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if not ok or user is None or not user.is_active:
        throttle.fail(ip)
        log.info("login_failed", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    throttle.reset(ip)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    s = get_settings()
    raw = new_session_token()
    now = utcnow()
    sess = UserSession(
        token_hash=sha256_hex(raw),
        user_id=user.id,
        csrf_token=new_csrf_token(),
        expires_at=now + dt.timedelta(hours=s.session_ttl_hours),
        ip=ip,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    user.last_login_at = now
    db.add(sess)
    db.commit()
    response.set_cookie(
        s.session_cookie_name,
        raw,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    log.info("login_ok", user_id=user.id, ip=ip)
    return MeOut(user=_user_out(user), auth="session", csrf_token=sess.csrf_token, scopes=list(SCOPES))


@router.post("/logout", status_code=204)
def logout(response: Response, principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    db.delete(principal.session)
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(current_principal)) -> MeOut:
    return MeOut(
        user=_user_out(principal.user),
        auth=principal.kind,
        csrf_token=principal.session.csrf_token if principal.session else None,
        scopes=sorted(principal.scopes),
    )


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChangeIn, principal: Principal = Depends(require_session), db: Session = Depends(get_db)
):
    user = principal.user
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    user.password_hash = hash_password(body.new_password)
    # Sign out every other browser.
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != principal.session.id))
    db.commit()
    log.info("password_changed", user_id=user.id)
    return Response(status_code=204)


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApiToken).where(ApiToken.user_id == principal.user.id).order_by(ApiToken.id.desc()))
    return [TokenOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/tokens", response_model=TokenCreatedOut, status_code=201)
def create_token(body: TokenCreateIn, principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    full, prefix, digest = new_api_token()
    expires = utcnow() + dt.timedelta(days=body.expires_in_days) if body.expires_in_days else None
    tok = ApiToken(
        user_id=principal.user.id, name=body.name, prefix=prefix, token_hash=digest, scopes=body.scopes, expires_at=expires
    )
    db.add(tok)
    db.commit()
    log.info("api_token_created", user_id=principal.user.id, token_id=tok.id, scopes=body.scopes)
    out = TokenOut.model_validate(tok, from_attributes=True).model_dump()
    return TokenCreatedOut(**out, token=full)


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, principal: Principal = Depends(require_session), db: Session = Depends(get_db)):
    tok = db.get(ApiToken, token_id)
    if tok is None or tok.user_id != principal.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    if tok.revoked_at is None:
        tok.revoked_at = utcnow()
        db.commit()
    return Response(status_code=204)
