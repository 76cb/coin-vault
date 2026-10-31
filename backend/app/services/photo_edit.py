"""Non-destructive photo edits: the original is never changed; edits are stored as settings and the
display copies (thumb, medium) are rendered from the original with them.

The browser editor (frontend/src/photoEdit.ts) runs the same steps on its preview, so what you see
while editing is what gets saved. Keep the two in step.

Order: orientation from EXIF -> quarter turns -> mirror -> straighten -> crop -> colour.
Colour on 0..1 values per channel:
  exposure     v *= 2 ** (exposure / 100)            (-100..100 = -1..+1 stop)
  contrast     v = (v - 0.5) * (1 + contrast / 100) + 0.5
  saturation   v = grey + (v - grey) * (1 + saturation / 100), grey = 0.2126 R + 0.7152 G + 0.0722 B
  warmth       R *= 1 + 0.15 w/100 ; B *= 1 - 0.15 w/100
  sharpness    v += 1.5 * s/100 * (v - box3x3(v)), on the output size
Straighten: rotate by `straighten` degrees (clockwise), then zoom so the frame has no empty corners.
Crop: x, y, w, h as fractions (0..1) of the straightened frame.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app.services import storage

TUNING = ("exposure", "contrast", "saturation", "warmth", "sharpness")


def edit_hash(edits: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(edits, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def edited_key(sha256: str, size: str, ehash: str) -> str:
    return f"derived/{sha256[:2]}/{sha256[2:4]}/{sha256}_{size}_e{ehash}.webp"


def straighten_zoom(w: float, h: float, degrees: float) -> float:
    """How much to enlarge a w x h image turned by `degrees` so it still fills a w x h frame."""
    a = math.radians(abs(degrees))
    c, s = math.cos(a), math.sin(a)
    return max((w * c + h * s) / w, (w * s + h * c) / h)


def _geometry(img: Image.Image, e: dict[str, Any]) -> Image.Image:
    turns = (int(e.get("rotate", 0)) // 90) % 4
    if turns:
        img = img.transpose([None, Image.Transpose.ROTATE_270, Image.Transpose.ROTATE_180, Image.Transpose.ROTATE_90][turns])
    if e.get("flip"):
        img = ImageOps.mirror(img)
    deg = float(e.get("straighten", 0) or 0)
    if deg:
        w, h = img.size
        k = straighten_zoom(w, h, deg)
        turned = img.rotate(-deg, resample=Image.Resampling.BICUBIC, expand=True)
        # 2 px in from the exact fit, so resampling at the edges never shows the empty corners
        fw, fh = max(1, int(w / k) - 2), max(1, int(h / k) - 2)
        left, top = (turned.width - fw) // 2, (turned.height - fh) // 2
        img = turned.crop((left, top, left + fw, top + fh))
    crop = e.get("crop")
    if crop:
        w, h = img.size
        box = (round(crop["x"] * w), round(crop["y"] * h), round((crop["x"] + crop["w"]) * w), round((crop["y"] + crop["h"]) * h))
        box = (max(0, box[0]), max(0, box[1]), min(w, max(box[0] + 1, box[2])), min(h, max(box[1] + 1, box[3])))
        img = img.crop(box)
    return img


def _box_blur(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    out = np.zeros_like(a)
    for dy in range(3):
        for dx in range(3):
            out += p[dy : dy + a.shape[0], dx : dx + a.shape[1]]
    return out / 9.0


def _colour(img: Image.Image, e: dict[str, Any]) -> Image.Image:
    if not any(e.get(k) for k in TUNING):
        return img
    alpha = img.getchannel("A") if img.mode == "RGBA" else None
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    exposure, contrast, sat, warm, sharp = (float(e.get(k, 0) or 0) for k in TUNING)
    if exposure:
        a *= 2 ** (exposure / 100)
    if contrast:
        a = (a - 0.5) * (1 + contrast / 100) + 0.5
    if sat:
        grey = (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722)[..., None]
        a = grey + (a - grey) * (1 + sat / 100)
    if warm:
        a[..., 0] *= 1 + 0.15 * warm / 100
        a[..., 2] *= 1 - 0.15 * warm / 100
    if sharp:
        a = np.clip(a, 0, 1)
        a = a + 1.5 * sharp / 100 * (a - _box_blur(a))
    out = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    if alpha is not None:
        out.putalpha(alpha)
    return out


def render(original: Image.Image, edits: dict[str, Any], edge: int | None) -> Image.Image:
    """The edited image, at most `edge` pixels on its long side (None: full size)."""
    img = ImageOps.exif_transpose(original)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = _geometry(img, edits)
    if edge:
        img.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return _colour(img, edits)  # sharpening is judged at the size shown


def write_edited(storage_key: str, sha256: str, edits: dict[str, Any]) -> tuple[str, int, int]:
    """Render and store the edited thumb and medium copies; returns (edit hash, full width, full height)."""
    ehash = edit_hash(edits)
    with Image.open(storage.path_for(storage_key)) as original:
        original.load()
        full = _geometry(ImageOps.exif_transpose(original), edits)
        width, height = full.size
        for size, edge in storage.DERIVED_SIZES.items():
            key = edited_key(sha256, size, ehash)
            if storage.exists(key):
                continue
            img = render(original, edits, edge)
            buf = io.BytesIO()
            img.save(buf, "WEBP", quality=82 if size == "thumb" else 88, method=4)
            storage.write_bytes(key, buf.getvalue())
    return ehash, width, height


def full_jpeg(storage_key: str, edits: dict[str, Any]) -> bytes:
    """The edited photo at full size, for download."""
    with Image.open(storage.path_for(storage_key)) as original:
        original.load()
        img = render(original, edits, None).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True)
    return buf.getvalue()


def display_size(storage_key: str) -> tuple[int, int]:
    """Width and height of the unedited photo as displayed (EXIF orientation applied)."""
    with Image.open(storage.path_for(storage_key)) as img:
        w, h = img.size
        orientation = img.getexif().get(0x0112, 1)
    return (h, w) if orientation in (5, 6, 7, 8) else (w, h)


def remove_edited(sha256: str, ehash: str) -> None:
    for size in storage.DERIVED_SIZES:
        storage.remove(edited_key(sha256, size, ehash))
