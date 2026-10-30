"""Password hashing (argon2id), token generation and hashing."""

import hashlib
import hmac
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with library defaults (RFC 9106 low-memory profile)

SCOPES = ("items:read", "items:write", "prices:read", "export")
MIN_PASSWORD_LENGTH = 10
TOKEN_PREFIX = "cv_"
_ALPHABET = string.ascii_lowercase + string.digits


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# Precomputed hash so failed logins for unknown users cost the same time as real ones.
DUMMY_HASH = hash_password("not-a-real-password-just-for-timing")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def new_api_token() -> tuple[str, str, str]:
    """Return (full_token, prefix, sha256_of_full_token). The full token is shown once."""
    prefix = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    secret = secrets.token_urlsafe(32)
    full = f"{TOKEN_PREFIX}{prefix}_{secret}"
    return full, prefix, sha256_hex(full)


def parse_api_token(token: str) -> str | None:
    """Return the prefix of a well-formed token, else None."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    rest = token[len(TOKEN_PREFIX):]
    prefix, sep, secret = rest.partition("_")
    if not sep or len(prefix) != 10 or not secret:
        return None
    return prefix


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
