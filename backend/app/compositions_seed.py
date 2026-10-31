"""Standard compositions (actual silver/gold/platinum/palladium weight).

ROWS_V1 is loaded by migration 0002; ROWS_V2 (bars by refiner, more bullion coins) by migration 0004.

Pure weight = gross weight (g) / 31.1034768 x fineness, rounded to 6 decimals, from each mint's
published specifications. Bullion uses the mint's stated pure content. Per-face rows give pure
metal per $1 of face value for junk/constant-content lots.
"""

from decimal import ROUND_HALF_UP, Decimal

TROY = Decimal("31.1034768")
Q = Decimal("0.000001")

US_MINT = "US Mint coin specifications (gross weight x fineness)"


def _pure(gross: str, fineness: str) -> Decimal:
    return (Decimal(gross) / TROY * Decimal(fineness)).quantize(Q, rounding=ROUND_HALF_UP)


def _coin(key, label, denom, y0, y1, metal, gross, fine, marks=None, country="United States", cite=US_MINT):
    return dict(
        key=key, label=label, country=country, denomination=denom, year_from=y0, year_to=y1, mint_marks=marks,
        metal=metal, fineness=Decimal(fine), gross_weight_g=Decimal(gross), pure_toz=_pure(gross, fine),
        per_face_unit=False, citation=cite,
    )


def _bullion(key, label, country, metal, gross, fine, pure, y0=None, cite="Issuing mint's bullion specification"):
    return dict(
        key=key, label=label, country=country, denomination=None, year_from=y0, year_to=None, mint_marks=None,
        metal=metal, fineness=Decimal(fine), gross_weight_g=Decimal(gross) if gross else None,
        pure_toz=Decimal(pure), per_face_unit=False, citation=cite,
    )


def _per_face(key, label, metal, fine, pure, cite):
    return dict(
        key=key, label=label, country="United States", denomination="$1 face", year_from=None, year_to=None,
        mint_marks=None, metal=metal, fineness=Decimal(fine), gross_weight_g=None, pure_toz=Decimal(pure),
        per_face_unit=True, citation=cite,
    )


_dime = _pure("2.50", "0.900")
_quarter = _pure("6.25", "0.900")
_half40 = _pure("11.50", "0.400")
_war_nickel = _pure("5.00", "0.350")

ROWS_V1 = [
    # US 90% silver
    _coin("us-dime-90", "US dime, 90% silver (1892–1964)", "10c", 1892, 1964, "Ag", "2.50", "0.900"),
    _coin("us-quarter-90", "US quarter, 90% silver (1892–1964)", "25c", 1892, 1964, "Ag", "6.25", "0.900"),
    _coin("us-half-90", "US half dollar, 90% silver (1892–1964)", "50c", 1892, 1964, "Ag", "12.50", "0.900"),
    _coin("us-dollar-90", "US Morgan / Peace dollar, 90% silver (1878–1935)", "$1", 1878, 1935, "Ag", "26.73", "0.900"),
    # US 40% and 35% silver
    _coin("us-half-40", "US Kennedy half, 40% silver (1965–1970)", "50c", 1965, 1970, "Ag", "11.50", "0.400"),
    _coin("us-ike-40", "US Eisenhower dollar, 40% silver collector issue (1971–1976-S)", "$1", 1971, 1976, "Ag", "24.59", "0.400", ["S"]),
    _coin("us-war-nickel-35", "US Jefferson war nickel, 35% silver (1942–1945, large mint mark)", "5c", 1942, 1945, "Ag", "5.00", "0.350", ["P", "D", "S"]),
    # US gold, pre-1933
    _coin("us-gold-20", "US $20 double eagle, 90% gold (1850–1933)", "$20", 1850, 1933, "Au", "33.436", "0.900"),
    _coin("us-gold-10", "US $10 eagle, 90% gold (1838–1933)", "$10", 1838, 1933, "Au", "16.718", "0.900"),
    _coin("us-gold-5", "US $5 half eagle, 90% gold (1839–1929)", "$5", 1839, 1929, "Au", "8.359", "0.900"),
    _coin("us-gold-2.5", "US $2.50 quarter eagle, 90% gold (1840–1929)", "$2.50", 1840, 1929, "Au", "4.18", "0.900"),
    _coin("us-gold-1", "US $1 gold dollar, 90% gold (1849–1889)", "$1", 1849, 1889, "Au", "1.672", "0.900"),
    # Junk silver lots, per $1 face value
    _per_face("us-90-per-face", "US 90% silver coins, per $1 face (full mint weight)", "Ag", "0.900", str(_quarter * 4), US_MINT),
    _per_face(
        "us-90-per-face-worn", "US 90% silver coins, per $1 face (circulated, dealer convention 0.715)", "Ag", "0.900", "0.715",
        "Common dealer allowance for wear on circulated 90% coin",
    ),
    _per_face("us-40-half-per-face", "US 40% Kennedy halves, per $1 face", "Ag", "0.400", str(_half40 * 2), US_MINT),
    _per_face("us-war-nickel-per-face", "US 35% war nickels, per $1 face", "Ag", "0.350", str(_war_nickel * 20), US_MINT),
    _per_face("us-dime-90-per-face", "US 90% dimes only, per $1 face", "Ag", "0.900", str(_dime * 10), US_MINT),
    # Bullion: silver
    _bullion("ase-1oz", "American Silver Eagle, 1 oz", "United States", "Ag", "31.103", "0.999", "1", 1986),
    _bullion("maple-ag-1oz", "Canadian Silver Maple Leaf, 1 oz", "Canada", "Ag", "31.11", "0.9999", "1", 1988),
    _bullion("britannia-ag-1oz", "British Silver Britannia, 1 oz (2013+)", "United Kingdom", "Ag", "31.21", "0.999", "1", 2013),
    _bullion("philharmonic-ag-1oz", "Austrian Silver Philharmonic, 1 oz", "Austria", "Ag", "31.103", "0.999", "1", 2008),
    _bullion("libertad-ag-1oz", "Mexican Silver Libertad, 1 oz", "Mexico", "Ag", "31.103", "0.999", "1"),
    _bullion("kangaroo-ag-1oz", "Australian Silver Kangaroo, 1 oz", "Australia", "Ag", None, "0.9999", "1", 2016),
    _bullion("panda-ag-30g", "Chinese Silver Panda, 30 g (2016+)", "China", "Ag", "30", "0.999", str(_pure("30", "0.999")), 2016),
    # Bullion: gold
    _bullion("age-1oz", "American Gold Eagle, 1 oz", "United States", "Au", "33.931", "0.9167", "1", 1986),
    _bullion("age-half", "American Gold Eagle, 1/2 oz", "United States", "Au", "16.966", "0.9167", "0.5", 1986),
    _bullion("age-quarter", "American Gold Eagle, 1/4 oz", "United States", "Au", "8.483", "0.9167", "0.25", 1986),
    _bullion("age-tenth", "American Gold Eagle, 1/10 oz", "United States", "Au", "3.393", "0.9167", "0.1", 1986),
    _bullion("buffalo-au-1oz", "American Gold Buffalo, 1 oz", "United States", "Au", "31.108", "0.9999", "1", 2006),
    _bullion("maple-au-1oz", "Canadian Gold Maple Leaf, 1 oz", "Canada", "Au", "31.11", "0.9999", "1", 1979),
    _bullion("krugerrand-1oz", "South African Krugerrand, 1 oz", "South Africa", "Au", "33.93", "0.9167", "1", 1967),
    _bullion("britannia-au-1oz", "British Gold Britannia, 1 oz", "United Kingdom", "Au", "31.21", "0.9999", "1", 2013),
    _bullion("philharmonic-au-1oz", "Austrian Gold Philharmonic, 1 oz", "Austria", "Au", "31.103", "0.9999", "1", 1989),
    # Bullion: platinum and palladium
    _bullion("ape-1oz", "American Platinum Eagle, 1 oz", "United States", "Pt", "31.120", "0.9995", "1", 1997),
    _bullion("maple-pt-1oz", "Canadian Platinum Maple Leaf, 1 oz", "Canada", "Pt", "31.11", "0.9995", "1"),
    _bullion("maple-pd-1oz", "Canadian Palladium Maple Leaf, 1 oz", "Canada", "Pd", "31.11", "0.9995", "1"),
]


# --- Version 2: bars by refiner and more bullion coins (migration 0004) --------------------

_SIZE_G = {"g": Decimal(1), "oz": TROY, "kg": Decimal(1000)}
_METAL_WORD = {"Au": "gold", "Ag": "silver", "Pt": "platinum", "Pd": "palladium"}


def _size(size: str) -> tuple[Decimal, str]:
    """'2.5 g' -> (2.5 g, '2.5 g'); '1 oz' -> (31.1034768 g, '1 oz'); '1/2 oz' works too."""
    amount, unit = size.split()
    if "/" in amount:
        a, b = amount.split("/")
        qty = Decimal(a) / Decimal(b)
    else:
        qty = Decimal(amount)
    return qty * _SIZE_G[unit], f"{amount} {unit}"


def _slug(t: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def _bar(refiner: str, metal: str, size: str, fine: str, cite: str, note: str = "") -> dict:
    gross, shown = _size(size)
    fine_d = Decimal(fine)
    shown_fine = str(fine_d.normalize()).lstrip("0") or "0"
    label = f"{refiner} {_METAL_WORD[metal]} bar, {shown} ({shown_fine}){note}"
    return dict(
        key=f"bar-{_slug(refiner)}-{metal.lower()}-{_slug(shown)}{'-' + _slug(note) if note else ''}",
        label=label, country=None, denomination="bar", year_from=None, year_to=None, mint_marks=None,
        metal=metal, fineness=fine_d, gross_weight_g=gross.quantize(Decimal("0.0001")),
        pure_toz=(gross / TROY * fine_d).quantize(Q, rounding=ROUND_HALF_UP), per_face_unit=False, citation=cite,
    )


def _product(label: str, metal: str, gross: str, fine: str, cite: str) -> dict:
    return dict(
        key=f"bar-{_slug(label)}", label=label, country=None, denomination="bar", year_from=None, year_to=None,
        mint_marks=None, metal=metal, fineness=Decimal(fine), gross_weight_g=Decimal(gross),
        pure_toz=_pure(gross, fine), per_face_unit=False, citation=cite,
    )


BAR_LINES: list[tuple[str, str, str, list[str], str]] = []  # (refiner, metal, fineness, sizes, source)
BAR_PRODUCTS: list[dict] = []
COINS_V2: list[dict] = []

ROWS_V2 = [_bar(r, m, size, f, src) for r, m, f, sizes, src in BAR_LINES for size in sizes] + BAR_PRODUCTS + COINS_V2

ROWS = ROWS_V1 + ROWS_V2
