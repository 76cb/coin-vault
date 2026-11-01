"""Finding a grading holder (slab) in a photo, and the perspective maths for straightening a tilted one.

A slab is the big four-sided object in the photo. Candidate outlines come from three places: the edges in
the photo (at a few sensitivities), its bright parts (a white insert or label), and whatever differs from
the background around the photo's border. Each candidate is reduced to four corners and kept only if its
corners are roughly square (a tilted rectangle) and edges in the photo run along all four sides. The
largest such outline wins, and each side is then fitted to the edge pixels along it, so rounded corners
and a slightly bowed edge don't pull it in.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image

DETECT_EDGE = 800  # long side the search runs at
MIN_AREA = 0.06  # of the photo
MIN_SUPPORT = 0.5  # share of each side that must lie on an edge in the photo


def perspective_coeffs(dst: list[tuple[float, float]], src: list[tuple[float, float]]) -> list[float]:
    """The 8 numbers PIL's PERSPECTIVE transform takes: for each output point (x, y) the input point is
    ((a x + b y + c) / (g x + h y + 1), (d x + e y + f) / (g x + h y + 1)), chosen so `dst[i]` maps to `src[i]`."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.append(v)
    return [float(c) for c in np.linalg.solve(np.array(rows, dtype=np.float64), np.array(rhs, dtype=np.float64))]


def straightened_size(corners: list[tuple[float, float]]) -> tuple[float, float]:
    """Width and height of the rectangle a quadrilateral (tl, tr, br, bl, in pixels) is straightened into:
    its longer top or bottom side, and its longer left or right side."""
    tl, tr, br, bl = (np.asarray(p, dtype=np.float64) for p in corners)
    w = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    h = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    return float(w), float(h)


def is_convex(corners: list[tuple[float, float]]) -> bool:
    """True for a quadrilateral whose corners go round one way (no crossed sides, no dents)."""
    pts = [np.asarray(p, dtype=np.float64) for p in corners]
    signs = []
    for i in range(4):
        a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
        u, v = b - a, c - b
        signs.append(float(u[0] * v[1] - u[1] * v[0]))
    return all(s > 0 for s in signs) or all(s < 0 for s in signs)


def _order(q: np.ndarray) -> np.ndarray:
    """Corners as top-left, top-right, bottom-right, bottom-left (going clockwise on screen)."""
    c = q.mean(axis=0)
    q = q[np.argsort(np.arctan2(q[:, 1] - c[1], q[:, 0] - c[0]))]  # clockwise on screen (y points down)
    return np.roll(q, -int(np.argmin(q.sum(axis=1))), axis=0)


def _angles_ok(q: np.ndarray, lo: float = 50, hi: float = 130) -> bool:
    for i in range(4):
        v1, v2 = q[i - 1] - q[i], q[(i + 1) % 4] - q[i]
        n = np.linalg.norm(v1) * np.linalg.norm(v2)
        if n == 0:
            return False
        if not lo <= math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(v1, v2)) / n)))) <= hi:
            return False
    return True


def _sides(q: np.ndarray, n: int = 80, keep: float = 0.8) -> list[np.ndarray]:
    """Points along the middle `keep` of each side (corners may be rounded)."""
    t = np.linspace((1 - keep) / 2, 1 - (1 - keep) / 2, n)[:, None]
    return [q[i] + t * (q[(i + 1) % 4] - q[i]) for i in range(4)]


def _support(near_edge: np.ndarray, q: np.ndarray) -> float:
    """The smallest share of any side that runs along an edge in the photo."""
    h, w = near_edge.shape
    worst = 1.0
    for pts in _sides(q):
        xs = np.clip(np.rint(pts[:, 0]).astype(int), 0, w - 1)
        ys = np.clip(np.rint(pts[:, 1]).astype(int), 0, h - 1)
        worst = min(worst, float(near_edge[ys, xs].mean()))
    return worst


def _quad_from(contour: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    for eps in (0.015, 0.02, 0.03, 0.04, 0.05, 0.07):
        ap = cv2.approxPolyDP(hull, eps * peri, True)
        if len(ap) == 4:
            return _order(ap.reshape(4, 2).astype(np.float64))
        if len(ap) < 4:
            return None
    return None


def _masks(rgb: np.ndarray, grey: np.ndarray) -> list[np.ndarray]:
    """Binary images whose outlines might be the slab's."""
    out = []
    blur = cv2.GaussianBlur(grey, (5, 5), 0)
    close = np.ones((5, 5), np.uint8)
    for lo, hi in ((20, 60), (40, 120), (70, 200)):
        out.append(cv2.morphologyEx(cv2.Canny(blur, lo, hi), cv2.MORPH_CLOSE, close, iterations=2))
    # bright parts: a white insert or a label
    _, bright = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out.append(cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2))
    # what differs from the background, judged from a strip round the photo's border
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    h, w = grey.shape
    b = max(4, min(h, w) // 25)
    border = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3), lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    dist = np.linalg.norm(lab - np.median(border, axis=0), axis=2)
    dist = cv2.GaussianBlur(dist, (7, 7), 0)
    dist8 = np.clip(dist * (255.0 / max(1.0, float(np.percentile(dist, 99)))), 0, 255).astype(np.uint8)
    _, differs = cv2.threshold(dist8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out.append(cv2.morphologyEx(differs, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8), iterations=2))
    return out


def _refine(edge_pts: np.ndarray, q: np.ndarray, band: float) -> np.ndarray:
    """Move each side onto the outermost strong edge near it, fit it there, and take the corners where the
    fitted sides meet. (A holder has an inner edge too; its outer rim is the one wanted. Rounded corners
    are left out of the fit, and the corners land where the straight sides would meet.)"""
    centre = q.mean(axis=0)
    lines = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        d = b - a
        length = float(np.linalg.norm(d))
        u = d / length
        n = np.array([-u[1], u[0]])
        if np.dot(n, (a + b) / 2 - centre) < 0:
            n = -n  # pointing out of the outline
        rel = edge_pts - a
        along = rel @ u
        across = rel @ n
        sel = (np.abs(across) <= band) & (along >= 0.12 * length) & (along <= 0.88 * length)
        if sel.sum() < 20:
            lines.append((a, u))  # too few edge pixels: keep the side as it was
            continue
        nb = int(math.ceil(band))
        hist = np.bincount(np.rint(across[sel]).astype(int) + nb, minlength=2 * nb + 1).astype(np.float64)
        hist = np.convolve(hist, np.ones(3) / 3, mode="same")
        strong = np.nonzero(hist >= 0.5 * hist.max())[0]
        offset = float(strong.max() - nb)  # the outermost of the strong edges
        near = sel & (np.abs(across - offset) <= 2.5)
        if near.sum() < 20:
            near = sel
        vx, vy, x0, y0 = cv2.fitLine(edge_pts[near].astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines.append((np.array([x0, y0], dtype=np.float64), np.array([vx, vy], dtype=np.float64)))
    out = []
    for i in range(4):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        m = np.array([d1, -d2]).T
        if abs(np.linalg.det(m)) < 1e-6:
            return q
        t = np.linalg.solve(m, p2 - p1)
        out.append(p1 + t[0] * d1)
    r = np.array(out)
    # a fit that moved a corner a long way is a fit to something else: keep the rough outline
    if np.max(np.linalg.norm(r - q, axis=1)) > band * 4:
        return q
    return r


def find_quad(img: Image.Image) -> list[tuple[float, float]] | None:
    """The slab's corners (top-left, top-right, bottom-right, bottom-left) as fractions of the image's
    width and height, or None when there isn't a clear four-sided outline."""
    rgb = np.asarray(img.convert("RGB"))
    h0, w0 = rgb.shape[:2]
    s = min(1.0, DETECT_EDGE / max(h0, w0))
    if s < 1:
        rgb = cv2.resize(rgb, (max(1, round(w0 * s)), max(1, round(h0 * s))), interpolation=cv2.INTER_AREA)
    h, w = rgb.shape[:2]
    if min(h, w) < 40:
        return None
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 30, 90)
    near_edge = cv2.dilate(edges, np.ones((5, 5), np.uint8)) > 0
    ys, xs = np.nonzero(edges)
    edge_pts = np.stack([xs, ys], axis=1).astype(np.float64)
    band = max(4.0, 0.025 * max(w, h))  # how far a rough side may be from the edge it stands for
    margin = 0.004 * max(w, h)
    best: tuple[float, np.ndarray] | None = None
    for mask in _masks(rgb, grey):
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            if cv2.contourArea(cv2.convexHull(c)) < MIN_AREA * w * h:
                continue
            q = _quad_from(c)
            if q is None or not _angles_ok(q):
                continue
            area = float(cv2.contourArea(q.astype(np.float32)))
            if not MIN_AREA * w * h <= area <= 0.97 * w * h:
                continue
            if (q[:, 0] < margin).any() or (q[:, 1] < margin).any() or (q[:, 0] > w - 1 - margin).any() or (q[:, 1] > h - 1 - margin).any():
                continue  # runs off the photo: not a whole holder
            q = _order(_refine(edge_pts, q, band))
            if not _angles_ok(q) or _support(near_edge, q) < MIN_SUPPORT:
                continue
            area = float(cv2.contourArea(q.astype(np.float32)))
            if best is None or area > best[0]:
                best = (area, q)
    if best is None:
        return None
    q = best[1]
    if not _angles_ok(q, 45, 135) or not is_convex([tuple(p) for p in q]):
        return None
    c = q.mean(axis=0)
    q = c + (q - c) * 1.006  # a hair outside the edge, so the holder's rim stays in
    q[:, 0] = np.clip(q[:, 0], 0, w)
    q[:, 1] = np.clip(q[:, 1], 0, h)
    return [(round(float(x) / w, 4), round(float(y) / h, 4)) for x, y in q]
