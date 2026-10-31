"""Reading barcodes from a photo (a holder's label), with zxing-cpp. Nothing leaves the server."""

from __future__ import annotations

import io

import zxingcpp
from PIL import Image, ImageOps

MAX_EDGE = 3000  # big enough for a label in a phone photo, small enough to stay quick


def read(data: bytes) -> list[dict[str, str]]:
    """Each barcode's text and format, most likely first; [] when none is found."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("L")
    except Exception as exc:  # noqa: BLE001 - any unreadable image is the same answer
        raise ValueError("That file isn't a photo that can be read") from exc
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    seen: dict[str, dict[str, str]] = {}
    for b in zxingcpp.read_barcodes(img):
        text = (b.text or "").strip()
        if b.valid and text and text not in seen:
            seen[text] = {"text": text, "format": str(b.format).split(".")[-1]}
    # a holder's barcode is a 1D code; put those before QR codes and the like
    return sorted(seen.values(), key=lambda x: x["format"].replace(" ", "").startswith(("QR", "MicroQR", "DataMatrix", "Aztec", "PDF417", "MaxiCode")))
