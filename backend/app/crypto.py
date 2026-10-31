"""AES-GCM encryption for secrets stored in the database (provider API keys)."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

VERSION = "v1"


class EncryptionUnavailable(RuntimeError):
    """CV_ENCRYPTION_KEY is missing or malformed."""


def generate_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def _key() -> bytes:
    raw = get_settings().encryption_key
    if not raw:
        raise EncryptionUnavailable(
            "CV_ENCRYPTION_KEY is not set, so API keys cannot be stored. "
            "Run update.sh (it adds one) or set it in /etc/coinvault/coinvault.env."
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise EncryptionUnavailable("CV_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != 32:
        raise EncryptionUnavailable("CV_ENCRYPTION_KEY must decode to 32 bytes")
    return key


def encrypt(plaintext: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plaintext.encode(), VERSION.encode())
    return f"{VERSION}:{base64.b64encode(nonce + ct).decode()}"


def decrypt(token: str) -> str:
    version, _, payload = token.partition(":")
    if version != VERSION:
        raise ValueError("unknown ciphertext version")
    blob = base64.b64decode(payload)
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], VERSION.encode()).decode()
