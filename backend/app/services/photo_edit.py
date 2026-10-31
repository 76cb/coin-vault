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
Circle (last): everything outside the circle inscribed in the crop becomes the background: clear
(transparent), white or black. The edge is anti-aliased (mask drawn at 4x, then reduced).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

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


BACKGROUNDS = {"white": (255, 255, 255), "black": (0, 0, 0)}


def _circle(img: Image.Image, e: dict[str, Any]) -> Image.Image:
    if not e.get("circle"):
        return img
    w, h = img.size
    big = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, w * 4 - 1, h * 4 - 1), fill=255)
    mask = big.resize((w, h), Image.Resampling.LANCZOS)
    rgb = img.convert("RGB")
    bg = e.get("background", "clear")
    if bg in BACKGROUNDS:
        out = Image.new("RGB", (w, h), BACKGROUNDS[bg])
        out.paste(rgb, (0, 0), mask)
        return out
    rgb.putalpha(mask)
    return rgb


def render(original: Image.Image, edits: dict[str, Any], edge: int | None) -> Image.Image:
    """The edited image, at most `edge` pixels on its long side (None: full size)."""
    img = ImageOps.exif_transpose(original)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img = _geometry(img, edits)
    if edge:
        img.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return _circle(_colour(img, edits), edits)  # sharpening is judged at the size shown


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


def full_image(storage_key: str, edits: dict[str, Any]) -> tuple[bytes, str, str]:
    """The edited photo at full size, for download: (bytes, media type, file extension).
    A JPEG, or a PNG when it's cut out as a circle on a clear background (a JPEG can't be transparent)."""
    with Image.open(storage.path_for(storage_key)) as original:
        original.load()
        img = render(original, edits, None)
    buf = io.BytesIO()
    if img.mode == "RGBA":
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue(), "image/png", "png"
    img.convert("RGB").save(buf, "JPEG", quality=92, optimize=True)
    return buf.getvalue(), "image/jpeg", "jpg"


# --- Finding the coin --------------------------------------------------------------------------

DETECT_EDGE = 256


def _sobel(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = np.pad(a, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return gx, gy


def _detect(img: Image.Image, edge: int, r_lo: float, r_hi: float, prefer_large: bool) -> tuple[float, float, float, float] | None:
    """(centre x, centre y, radius, score) in the image's pixels; radii searched as fractions of its shorter side."""
    small = img.convert("L")
    small.thumbnail((edge, edge), Image.Resampling.BILINEAR)
    scale = img.width / small.width
    small = small.filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(small, dtype=np.float32)
    h, w = a.shape
    m = min(h, w)
    if m < 24:
        return None
    gx, gy = _sobel(a)
    mag = np.hypot(gx, gy)
    thr = max(float(np.percentile(mag, 90)), float(mag.max()) * 0.1)
    ys, xs = np.nonzero(mag > thr)
    if len(xs) < 40:
        return None
    dx = gx[ys, xs] / mag[ys, xs]
    dy = gy[ys, xs] / mag[ys, xs]
    xs = xs.astype(np.float32)
    ys = ys.astype(np.float32)
    found: list[tuple[float, int, int, int]] = []  # score, r, cx, cy
    for r in range(max(6, int(m * r_lo)), int(m * r_hi) + 1):
        for sign in (1.0, -1.0):
            cx = np.rint(xs + sign * r * dx).astype(np.int32)
            cy = np.rint(ys + sign * r * dy).astype(np.int32)
            ok = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
            if not ok.any():
                continue
            acc = np.bincount(cy[ok] * w + cx[ok], minlength=w * h).reshape(h, w).astype(np.float32)
            p = np.pad(acc, 1)
            acc = sum(p[i : i + h, j : j + w] for i in range(3) for j in range(3))  # a pixel's slack either way
            k = int(acc.argmax())
            found.append((float(acc.flat[k]) / (2 * math.pi * r), r, k % w, k // w))
    if not found:
        return None
    best = max(f[0] for f in found)
    pick = max((f for f in found if f[0] >= best * 0.8), key=lambda f: f[1]) if prefer_large else max(found)
    score, r, cx, cy = pick
    return (cx + 0.5) * scale, (cy + 0.5) * scale, r * scale, score


def find_circle(img: Image.Image) -> tuple[float, float, float, float] | None:
    """The coin's outline: (centre x, centre y, radius) as fractions of the image's width, height and
    shorter side, and a score; None when no clear circle is found.

    A gradient Hough transform: each strong edge votes for the centre one radius along its gradient
    (inwards for a light coin on a dark background, outwards for the opposite), and the circle with the
    most support for its size wins. First on a small copy of the whole photo, preferring the largest of
    the nearly-as-good circles so the rim beats circles in the design; then again on a sharper copy of
    just that area, within a few percent of that size, to fit the rim closely.
    """
    coarse = _detect(img, DETECT_EDGE, 0.15, 0.56, prefer_large=True)
    if coarse is None or coarse[3] < 0.35:
        return None
    cx, cy, r, score = coarse
    half = r * 1.35
    box = (max(0, int(cx - half)), max(0, int(cy - half)), min(img.width, int(cx + half) + 1), min(img.height, int(cy + half) + 1))
    sub = img.crop(box)
    sm = min(sub.size)
    fine = _detect(sub, 512, r * 0.94 / sm, r * 1.06 / sm, prefer_large=False) if sm >= 48 else None
    if fine is not None and fine[3] >= 0.2:  # sharper edges are thinner, so fewer votes: a lower bar
        cx, cy, r, score = box[0] + fine[0], box[1] + fine[1], fine[2], fine[3]
    return cx / img.width, cy / img.height, r / min(img.size), score


def find_coin_crop(storage_key: str, edits: dict[str, Any]) -> dict[str, float] | None:
    """A square crop, in fractions of the frame after the turns and straighten in `edits`, that just holds
    the coin; None when no coin outline is found."""
    with Image.open(storage.path_for(storage_key)) as original:
        original.draft("RGB", (1200, 1200))  # JPEGs decode at a fraction of full size: much faster
        img = ImageOps.exif_transpose(original)
        img = img.convert("RGB")
    img.thumbnail((1200, 1200))
    frame = _geometry(img, {k: v for k, v in edits.items() if k in ("rotate", "flip", "straighten")})
    hit = find_circle(frame)
    if hit is None:
        return None
    fx, fy, fr, _ = hit
    fw, fh = frame.size
    side = 2 * fr * min(fw, fh) * 1.005  # pixels: the rim, and not much else
    side = min(side, fw, fh)
    cx, cy = fx * fw, fy * fh
    x = min(max(cx - side / 2, 0), fw - side)
    y = min(max(cy - side / 2, 0), fh - side)
    return {"x": round(x / fw, 4), "y": round(y / fh, 4), "w": round(side / fw, 4), "h": round(side / fh, 4)}


def display_size(storage_key: str) -> tuple[int, int]:
    """Width and height of the unedited photo as displayed (EXIF orientation applied)."""
    with Image.open(storage.path_for(storage_key)) as img:
        w, h = img.size
        orientation = img.getexif().get(0x0112, 1)
    return (h, w) if orientation in (5, 6, 7, 8) else (w, h)


def remove_edited(sha256: str, ehash: str) -> None:
    for size in storage.DERIVED_SIZES:
        storage.remove(edited_key(sha256, size, ehash))
