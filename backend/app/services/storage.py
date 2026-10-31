"""Content-addressed file storage under MEDIA_ROOT. Files never live in the database."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.config import get_settings

DERIVED_SIZES = {"thumb": 400, "medium": 1600}


def media_root() -> Path:
    root = Path(get_settings().media_root).resolve()
    return root


def ensure_dirs() -> None:
    for sub in ("originals", "derived", "documents"):
        (media_root() / sub).mkdir(parents=True, exist_ok=True)


def original_key(sha256: str, ext: str, area: str = "originals") -> str:
    return f"{area}/{sha256[:2]}/{sha256[2:4]}/{sha256}.{ext}"


def derived_key(sha256: str, size: str) -> str:
    return f"derived/{sha256[:2]}/{sha256[2:4]}/{sha256}_{size}.webp"


def path_for(key: str) -> Path:
    root = media_root()
    p = (root / key).resolve()
    if root not in p.parents:
        raise ValueError("storage key escapes media root")
    return p


def exists(key: str) -> bool:
    return path_for(key).exists()


FILE_MODE = 0o640


def write_bytes(key: str, data: bytes) -> None:
    """Atomic write; content-addressed keys mean an existing file already has these bytes."""
    p = path_for(key)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        # mkstemp creates 0600 files; nginx serves media through the coinvault group (X-Accel), so it needs g+r.
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def remove(key: str) -> None:
    path_for(key).unlink(missing_ok=True)
