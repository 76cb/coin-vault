"""Image and document intake: content sniffing, GPS stripping, derivatives, quality and perceptual hash.

Originals keep full quality. JPEG GPS data is removed losslessly (the image data is untouched);
orientation is applied only to the display copies. HEIC/HEIF (common from phones) is converted
to a high-quality JPEG original because browsers cannot display HEIC.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import Any

import filetype
import imagehash
import numpy as np
import piexif
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.services import storage

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 150_000_000  # guard against decompression bombs

IMAGE_MIMES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heic",
    "image/avif": "avif",
}
DOCUMENT_MIMES = {"application/pdf": "pdf", **{k: v for k, v in IMAGE_MIMES.items()}}

GPS_IFD = 0x8825

# Quality thresholds. Defaults are generic; tune them against your own camera in settings later.
BLUR_WARN = 60.0  # variance of Laplacian on a 1024-px grayscale copy
GLARE_WARN = 0.02  # share of pixels at or near pure white
MIN_SIDE_WARN = 1200  # pixels on the shorter side
DARK_WARN = 40.0  # mean brightness 0-255


class IntakeError(ValueError):
    """Raised for files that must be rejected (wrong type, too large, unreadable)."""


@dataclass
class StoredImage:
    storage_key: str
    sha256: str
    mime: str
    width: int
    height: int
    bytes: int
    phash: str
    quality: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoredDocument:
    storage_key: str
    sha256: str
    mime: str
    bytes: int


def sniff(data: bytes) -> str | None:
    kind = filetype.guess(data)
    if kind is not None:
        return kind.mime
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return None


def _strip_jpeg_gps(data: bytes) -> bytes:
    try:
        exif = piexif.load(data)
    except Exception:
        return data
    if not exif.get("GPS"):
        return data
    exif["GPS"] = {}
    exif["0th"].pop(piexif.ImageIFD.GPSTag, None)
    try:
        out = io.BytesIO()
        piexif.insert(piexif.dump(exif), data, out)
        return out.getvalue()
    except Exception:
        # Malformed EXIF that piexif cannot re-dump: drop EXIF entirely, still lossless.
        out = io.BytesIO()
        piexif.remove(data, out)
        return out.getvalue()


def _has_gps(img: Image.Image) -> bool:
    try:
        return bool(img.getexif().get_ifd(GPS_IFD))
    except Exception:
        return False


def _normalise_original(data: bytes, mime: str) -> tuple[bytes, str, bool]:
    """Return (bytes_to_store, mime, gps_removed)."""
    if mime == "image/jpeg":
        stripped = _strip_jpeg_gps(data)
        return stripped, mime, stripped != data
    img = Image.open(io.BytesIO(data))
    if mime in ("image/heic", "image/heif", "image/avif"):
        img = ImageOps.exif_transpose(img).convert("RGB")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=95, subsampling=0)
        return out.getvalue(), "image/jpeg", True
    if _has_gps(img):
        exif = img.getexif()
        del exif[GPS_IFD]
        out = io.BytesIO()
        if mime == "image/png":
            img.save(out, "PNG", exif=exif.tobytes())
        else:  # webp
            img.save(out, "WEBP", lossless=True, exif=exif.tobytes())
        return out.getvalue(), mime, True
    return data, mime, False


def _laplacian_variance(gray: np.ndarray) -> float:
    c = gray[1:-1, 1:-1]
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * c
    return float(lap.var())


def assess_quality(img: Image.Image) -> dict[str, Any]:
    w, h = img.size
    small = img.convert("L")
    small.thumbnail((1024, 1024))
    gray = np.asarray(small, dtype=np.float32)
    blur = _laplacian_variance(gray)
    glare = float((gray >= 250).mean())
    brightness = float(gray.mean())
    checks: list[dict[str, str]] = []
    if blur < BLUR_WARN:
        checks.append({"check": "blur", "advice": "Looks soft. Refocus, add light, or steady the stand."})
    if glare > GLARE_WARN:
        checks.append({"check": "glare", "advice": "Highlights are blown out. Diffuse or angle the light."})
    if min(w, h) < MIN_SIDE_WARN:
        checks.append({"check": "resolution", "advice": "Low resolution. Move closer or raise camera resolution."})
    if brightness < DARK_WARN:
        checks.append({"check": "exposure", "advice": "Underexposed. Add light or raise exposure."})
    return {
        "verdict": "warn" if checks else "pass",
        "blur_score": round(blur, 1),
        "glare_fraction": round(glare, 4),
        "brightness": round(brightness, 1),
        "min_side_px": min(w, h),
        "issues": checks,
    }


def store_image(data: bytes, max_bytes: int) -> StoredImage:
    if len(data) > max_bytes:
        raise IntakeError(f"File is larger than {max_bytes // (1024 * 1024)} MB")
    mime = sniff(data)
    if mime not in IMAGE_MIMES:
        raise IntakeError("Not a supported image (JPEG, PNG, WebP, HEIC or AVIF)")
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()
        stored, mime, gps_removed = _normalise_original(data, mime)
        img = Image.open(io.BytesIO(stored))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise IntakeError(f"Image could not be read: {exc}") from exc

    sha = hashlib.sha256(stored).hexdigest()
    key = storage.original_key(sha, IMAGE_MIMES[mime])
    storage.write_bytes(key, stored)

    display = ImageOps.exif_transpose(img)
    if display.mode not in ("RGB", "RGBA"):
        display = display.convert("RGB")
    for size, edge in storage.DERIVED_SIZES.items():
        dkey = storage.derived_key(sha, size)
        if storage.exists(dkey):
            continue
        copy = display.copy()
        copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        copy.save(buf, "WEBP", quality=82 if size == "thumb" else 88, method=4)
        storage.write_bytes(dkey, buf.getvalue())

    quality = assess_quality(display)
    quality["gps_removed"] = gps_removed
    return StoredImage(
        storage_key=key,
        sha256=sha,
        mime=mime,
        width=display.width,
        height=display.height,
        bytes=len(stored),
        phash=str(imagehash.phash(display)),
        quality=quality,
    )


def store_document(data: bytes, max_bytes: int) -> StoredDocument:
    if len(data) > max_bytes:
        raise IntakeError(f"File is larger than {max_bytes // (1024 * 1024)} MB")
    mime = sniff(data)
    if mime not in DOCUMENT_MIMES:
        raise IntakeError("Documents must be PDF or an image (JPEG, PNG, WebP, HEIC)")
    if mime != "application/pdf":
        try:
            Image.open(io.BytesIO(data)).verify()
            data, mime, _ = _normalise_original(data, mime)
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise IntakeError(f"Image could not be read: {exc}") from exc
    elif b"%%EOF" not in data[-2048:]:
        raise IntakeError("PDF looks truncated or damaged")
    sha = hashlib.sha256(data).hexdigest()
    key = storage.original_key(sha, DOCUMENT_MIMES[mime], area="documents")
    storage.write_bytes(key, data)
    return StoredDocument(storage_key=key, sha256=sha, mime=mime, bytes=len(data))


def phash_distance(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)
