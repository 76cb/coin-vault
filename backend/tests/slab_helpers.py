"""A made-up photo of a grading holder lying at an angle on a table, for testing slab finding."""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.services.slab import perspective_coeffs


def slab_image(seed=1, W=1600, H=1200, corners=None, kind="ngc", bg="wood"):
    rnd = np.random.default_rng(seed)
    # background
    yy, xx = np.mgrid[0:H, 0:W]
    if bg == "wood":
        base = np.array([70, 45, 30], float)
        streak = 18 * np.sin(yy / 7.0 + 3 * np.sin(xx / 150.0)) + 10 * np.sin(yy / 23.0)
        img = base[None, None, :] + streak[..., None] * np.array([1, 0.7, 0.5]) + rnd.normal(0, 6, (H, W, 1))
    else:
        img = np.full((H, W, 3), (205, 205, 200), float) + rnd.normal(0, 4, (H, W, 1))
    bgimg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    # slab on a flat canvas: 600 x 800 (3:4 like a holder)
    sw, sh = 600, 800
    slab = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(slab)
    d.rounded_rectangle((0, 0, sw - 1, sh - 1), radius=60, fill=(230, 232, 235, 70), outline=(250, 250, 250, 255), width=6)
    d.rounded_rectangle((8, 8, sw - 9, sh - 9), radius=54, outline=(60, 60, 60, 160), width=3)
    if kind == "ngc":
        d.rectangle((45, 45, sw - 46, sh - 46), fill=(240, 240, 238, 255))
    else:  # clear PCGS-like: only a label, clear around the coin
        d.rectangle((45, 45, sw - 46, sh - 46), outline=(220, 220, 220, 200), width=3)
    d.rectangle((60, 60, sw - 61, 260), fill=(225, 215, 190, 255))
    for i in range(6):
        d.rectangle((90, 90 + i * 25, 90 + rnd.integers(150, 380), 100 + i * 25), fill=(40, 40, 40, 255))
    d.ellipse((sw / 2 - 140, 400, sw / 2 + 140, 680), fill=(190, 110, 70, 255))
    if corners is None:
        corners = [(500, 220), (1100, 240), (1130, 1060), (470, 1040)]
    inv = perspective_coeffs(corners, [(0, 0), (sw, 0), (sw, sh), (0, sh)])  # photo -> holder
    warped = slab.transform((W, H), Image.Transform.PERSPECTIVE, inv, Image.Resampling.BICUBIC)
    bgimg.paste(warped, (0, 0), warped)
    return bgimg.filter(ImageFilter.GaussianBlur(0.8)), corners
