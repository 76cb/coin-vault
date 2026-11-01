"""Goldbacks: notes with a layer of 24-karat gold, issued in series named for a state or region.

One Goldback holds 1/1000 troy ounce of gold, so a note of denomination n holds n/1000 ozt
(https://en.wikipedia.org/wiki/Goldback: specifications and the series table, with each series' first printing).
"""

from __future__ import annotations

from decimal import Decimal

SOURCE = "https://en.wikipedia.org/wiki/Goldback"
OZT_PER_GOLDBACK = Decimal("0.001")
FINENESS = Decimal("0.9999")  # 24-karat; dealers list them as .9999 gold (e.g. https://www.moneymetals.com/nevada-goldback-gold-note-bundle/1008)
GRAMS_PER_TOZ = Decimal("31.1034768")

# denominations in Goldbacks; 1/4 and 3 exist but are uncommon
DENOMINATIONS: list[Decimal] = [Decimal(v) for v in ("0.25", "0.5", "1", "2", "3", "5", "10", "25", "50", "100")]
COMMON = [Decimal(v) for v in ("0.5", "1", "2", "5", "10", "25", "50", "100")]

# (series name, year of first printing)
SERIES: list[tuple[str, int]] = [
    ("Utah", 2019), ("Nevada", 2020), ("New Hampshire", 2020), ("Wyoming", 2022), ("South Dakota", 2023),
    ("Florida", 2025), ("Oklahoma", 2025), ("Arizona", 2025), ("Dallas Fort Worth", 2025), ("Idaho", 2026),
    ("California", 2026), ("Ohio", 2026), ("Washington D.C.", 2026), ("Colorado", 2026),
]


def gold_toz(denomination: Decimal | None) -> Decimal | None:
    """Troy ounces of gold in one note of this denomination."""
    return None if denomination is None else (Decimal(denomination) * OZT_PER_GOLDBACK).quantize(Decimal("0.000001"))


def gold_grams(denomination: Decimal | None) -> Decimal | None:
    """The gold layer's weight in grams for one note."""
    oz = gold_toz(denomination)
    return None if oz is None else (oz * GRAMS_PER_TOZ).quantize(Decimal("0.000001"))


def denomination_label(d: Decimal | float | str | None) -> str:
    """1/2, 1/4 or a whole number, as a person writes it."""
    if d is None:
        return ""
    v = Decimal(str(d)).normalize()
    return {"0.5": "1/2", "0.25": "1/4"}.get(format(v, "f"), format(v, "f"))


def title(state: str | None, denomination: Decimal | None, year: int | None) -> str:
    return " ".join(x for x in (str(year) if year else "", state or "", "Goldback", denomination_label(denomination)) if x)
