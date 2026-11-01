"""Standard compositions (actual silver/gold/platinum/palladium weight).

ROWS_V1 is loaded by migration 0002; ROWS_V2 (bars by refiner, more bullion coins) by migration 0004,
ROWS_V3 (US silver proofs) by 0005, ROWS_V4 (the world catalogue, app/data/catalogue) by 0006
ROWS_V5 (more of the catalogue) by 0007 and ROWS_V6 (Perth Mint platinum Lunar coins) by 0011.

Pure weight = gross weight (g) / 31.1034768 x fineness, rounded to 6 decimals, from each mint's
published specifications. Bullion uses the mint's stated pure content. Per-face rows give pure
metal per $1 of face value for junk/constant-content lots.
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

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
        key=f"bar-{_slug(refiner)}-{metal.lower()}-{_slug(shown)}-{str(fine_d.normalize()).replace('0.', '')}",
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



CHECKED = "checked 2026-10-31"
VALCAMBI_MINTED = f"Valcambi minted bars, valcambi.com/product/minted-bars ({CHECKED})"
VALCAMBI_CAST = f"Valcambi cast bars, valcambi.com/product/cast-bars ({CHECKED})"
VALCAMBI_COMBI = f"Valcambi CombiBar, valcambi.com/product/combibar ({CHECKED})"
HERAEUS = f"Heraeus precious metal bars, heraeus-precious-metals.com ({CHECKED})"
ARGOR = f"Argor-Heraeus cast and minted bars brochure 2025, argor-heraeus.com ({CHECKED})"
PERTH = f"The Perth Mint 2026 bullion brochure ({CHECKED})"
PERTH_COIN = f"The Perth Mint product page and bullion brochure ({CHECKED})"
RCM = f"Royal Canadian Mint, mint.ca and 2016 bullion brochure ({CHECKED})"
ROYAL_MINT = f"The Royal Mint, royalmint.com/invest/bars ({CHECKED})"
SOVEREIGN = f"The Royal Mint, sovereign weights (gross x 916.7 fine) ({CHECKED})"
AUSTRIAN = f"Muenze Oesterreich price list ({CHECKED})"
PAMP_DEALER = f"PAMP Lady Fortuna, dealer listings (Suisse Gold; APMEX for 100 g) - pamp.com unreadable ({CHECKED})"
SUNSHINE = f"Sunshine Minting, dealer listing (APMEX) ({CHECKED})"
ASAHI = f"Asahi Refining, dealer listing (Suisse Gold) ({CHECKED})"
US_MINT_PD = f"US Mint, American Palladium Eagle ({CHECKED})"
APMEX_CORONA = f"APMEX spec sheet; Muenze Oesterreich lists 30.49 g fine ({CHECKED})"

BAR_LINES = [
    ("Valcambi", "Au", "0.9999", ["1 g", "2.5 g", "5 g", "10 g", "20 g", "1 oz", "50 g", "100 g", "250 g", "10 oz", "500 g", "1 kg"], VALCAMBI_MINTED),
    ("Valcambi", "Au", "0.999", ["50 g", "100 g", "1 kg"], VALCAMBI_CAST),
    ("Valcambi", "Au", "0.995", ["50 g", "100 g", "1 kg", "100 oz"], VALCAMBI_CAST),
    ("Valcambi", "Ag", "0.999", ["1 oz", "50 g", "100 g", "500 g", "1 kg", "10 oz", "100 oz", "5 kg", "15 kg"], VALCAMBI_MINTED + "; " + VALCAMBI_CAST),
    ("Valcambi", "Ag", "0.9999", ["1 kg"], VALCAMBI_CAST),
    ("Valcambi", "Pt", "0.9995", ["1 g", "2.5 g", "5 g", "10 g", "20 g", "1 oz", "50 g", "100 g", "500 g", "1 kg"], VALCAMBI_MINTED),
    ("Valcambi", "Pd", "0.9995", ["1 oz", "50 g", "100 g", "500 g", "1 kg"], VALCAMBI_MINTED),
    ("PAMP Suisse", "Au", "0.9999", ["1 g", "2.5 g", "5 g", "10 g", "20 g", "100 g"], PAMP_DEALER),
    ("Argor-Heraeus", "Au", "0.9999", ["1 g", "2 g", "5 g", "10 g", "20 g", "1 oz", "50 g", "100 g"], ARGOR),
    ("Heraeus", "Au", "0.9999", ["1 g", "2 g", "5 g", "10 g", "20 g", "1 oz", "50 g", "100 g", "250 g", "500 g", "1 kg"], HERAEUS),
    ("Heraeus", "Ag", "0.9999", ["1 oz", "100 g", "250 g", "500 g", "1 kg", "5 kg", "15 kg"], HERAEUS),
    ("Heraeus", "Pt", "0.9995", ["1 oz", "100 g", "500 g", "1 kg"], HERAEUS),
    ("Heraeus", "Pd", "0.9995", ["1 oz", "100 g", "500 g", "1 kg"], HERAEUS),
    ("Perth Mint", "Au", "0.9999", ["1 g", "5 g", "10 g", "20 g", "1 oz", "50 g", "100 g", "10 oz", "1 kg"], PERTH),
    ("Perth Mint", "Ag", "0.9999", ["1 kg"], PERTH),
    ("Royal Canadian Mint", "Au", "0.9999", ["10 g", "1 oz", "50 g", "100 g"], RCM),
    ("Royal Canadian Mint", "Ag", "0.9999", ["10 oz", "100 oz"], RCM),
    ("The Royal Mint", "Au", "0.9999", ["1 g", "5 g", "10 g", "20 g", "50 g", "100 g"], ROYAL_MINT),
    ("Austrian Mint", "Au", "0.9999", ["1 g", "2 g", "5 g", "10 g", "20 g", "50 g", "100 g", "250 g", "500 g", "1 kg"], AUSTRIAN),
    ("Sunshine Minting", "Ag", "0.999", ["1 oz", "5 oz", "10 oz", "100 oz"], SUNSHINE),
    ("Asahi", "Au", "0.9999", ["1 oz", "10 oz"], ASAHI),
    ("Asahi", "Ag", "0.999", ["10 oz", "100 oz", "1 kg"], ASAHI),
]

BAR_PRODUCTS = [
    _product("Valcambi Gold CombiBar 5 x 1 g", "Au", "5", "0.9999", VALCAMBI_COMBI),
    _product("Valcambi Gold CombiBar 20 x 1 g", "Au", "20", "0.9999", VALCAMBI_COMBI),
    _product("Valcambi Gold CombiBar 10 x 1/10 oz (1 oz)", "Au", "31.1035", "0.9999", VALCAMBI_COMBI),
    _product("Valcambi Gold CombiBar 50 x 1 g", "Au", "50", "0.9999", VALCAMBI_COMBI),
    _product("Valcambi Gold CombiBar 100 x 1 g", "Au", "100", "0.9999", VALCAMBI_COMBI),
    _product("Valcambi Silver CombiBar 100 x 1 g", "Ag", "100", "0.999", VALCAMBI_COMBI),
    _product("Valcambi Silver CombiBar 10 x 10 g", "Ag", "100", "0.999", VALCAMBI_COMBI),
    _product("Valcambi Silver CombiBar Skyline 3 x 1 oz", "Ag", "93.3104", "0.999", VALCAMBI_COMBI),
    _product("Valcambi Silver CombiBar Skyline 16 x 1/4 oz", "Ag", "124.4139", "0.999", VALCAMBI_COMBI),
    _product("Valcambi Platinum CombiBar 50 x 1 g", "Pt", "50", "0.9995", VALCAMBI_COMBI),
    _product("Valcambi Palladium CombiBar 50 x 1 g", "Pd", "50", "0.9995", VALCAMBI_COMBI),
    _product("Heraeus Gold CombiBar 20 x 1 g", "Au", "20", "0.9999", HERAEUS),
    _product("Heraeus Gold CombiBar 50 x 1 g", "Au", "50", "0.9999", HERAEUS),
    _product("Heraeus Gold CombiBar 100 x 1 g", "Au", "100", "0.9999", HERAEUS),
    _product("Heraeus Gold MultiDisc 10 x 1 g", "Au", "10", "0.9999", HERAEUS),
]

COINS_V2 = [
    _bullion("kookaburra-ag-1oz", "Australian Silver Kookaburra, 1 oz", "Australia", "Ag", "31.107", "0.9999", "1", cite=PERTH_COIN),
    _bullion("lunar3-ag-1oz", "Australian Lunar Series III Silver, 1 oz", "Australia", "Ag", None, "0.9999", "1", cite=f"APMEX product page ({CHECKED})"),
    _bullion("kangaroo-au-1oz", "Australian Gold Kangaroo, 1 oz", "Australia", "Au", "31.107", "0.9999", "1", cite=PERTH_COIN),
    _bullion("maple-au-half", "Canadian Gold Maple Leaf, 1/2 oz", "Canada", "Au", "15.55", "0.9999", "0.5", cite=RCM),
    _bullion("maple-au-quarter", "Canadian Gold Maple Leaf, 1/4 oz", "Canada", "Au", "7.77", "0.9999", "0.25", cite=RCM),
    _bullion("maple-au-tenth", "Canadian Gold Maple Leaf, 1/10 oz", "Canada", "Au", "3.11", "0.9999", "0.1", cite=RCM),
    _bullion("maple-au-twentieth", "Canadian Gold Maple Leaf, 1/20 oz", "Canada", "Au", "1.55", "0.9999", "0.05", cite=RCM),
    _bullion("ape-pd-1oz", "American Palladium Eagle, 1 oz", "United States", "Pd", "31.120", "0.9995", "1", 2017, cite=US_MINT_PD),
    _bullion("sovereign-full", "British Gold Sovereign", "United Kingdom", "Au", "7.98", "0.9167", "0.2354", cite=SOVEREIGN),
    _bullion("sovereign-half", "British Gold Half Sovereign", "United Kingdom", "Au", "3.99", "0.9167", "0.1177", cite=SOVEREIGN),
    _bullion("sovereign-quarter", "British Gold Quarter Sovereign", "United Kingdom", "Au", "2", "0.9167", "0.0589", cite=SOVEREIGN),
    _bullion("sovereign-double", "British Gold Double Sovereign", "United Kingdom", "Au", "15.98", "0.9167", "0.4709", cite=SOVEREIGN),
    _bullion("corona-100-au", "Austrian 100 Corona (1915 restrike)", "Austria", "Au", "33.875", "0.900", "0.9802", cite=APMEX_CORONA),
]

ROWS_V2 = [_bar(r, m, size, f, src) for r, m, f, sizes, src in BAR_LINES for size in sizes] + BAR_PRODUCTS + COINS_V2


# --- Version 3: modern US silver proofs and the 40% Bicentennial coins (migration 0005) -----
# Only suggested when the text says "silver": copper-nickel proofs share the same years and mint mark.

US_MINT_999 = f"US Mint via CoinNews (quarter 6.343 g, 99.9% silver); Greysheet specs for dime 2.537 g and half 12.685 g ({CHECKED})"
ROWS_V3 = [
    _coin("us-silver-proof-dime-90", "US silver proof dime, 90% silver (1992–2018-S)", "10c", 1992, 2018, "Ag", "2.50", "0.900", ["S"]),
    _coin("us-silver-proof-quarter-90", "US silver proof quarter, 90% silver (1992–2018-S)", "25c", 1992, 2018, "Ag", "6.25", "0.900", ["S"]),
    _coin("us-silver-proof-half-90", "US silver proof half dollar, 90% silver (1992–2018-S)", "50c", 1992, 2018, "Ag", "12.50", "0.900", ["S"]),
    _coin("us-silver-proof-dime-999", "US silver proof dime, .999 silver (2019-S on)", "10c", 2019, None, "Ag", "2.537", "0.999", ["S"], cite=US_MINT_999),
    _coin("us-silver-proof-quarter-999", "US silver proof quarter, .999 silver (2019-S on)", "25c", 2019, None, "Ag", "6.343", "0.999", ["S"], cite=US_MINT_999),
    _coin("us-silver-proof-half-999", "US silver proof half dollar, .999 silver (2019-S on)", "50c", 2019, None, "Ag", "12.685", "0.999", ["S"], cite=US_MINT_999),
    _coin("us-bicentennial-quarter-40", "US Bicentennial quarter, 40% silver (1776–1976-S)", "25c", 1975, 1976, "Ag", "5.75", "0.400", ["S"]),
    _coin("us-bicentennial-half-40", "US Bicentennial half dollar, 40% silver (1776–1976-S)", "50c", 1975, 1976, "Ag", "11.50", "0.400", ["S"]),
]

_D90, _Q90, _H90 = _pure("2.50", "0.900"), _pure("6.25", "0.900"), _pure("12.50", "0.900")
_D999, _Q999, _H999 = _pure("2.537", "0.999"), _pure("6.343", "0.999"), _pure("12.685", "0.999")
SET_CITE = "Sum of the set's silver coins (per-coin specs above); clad cent, nickel and dollars carry no silver"


def _set(key, label, y0, y1, pure):
    return dict(
        key=key, label=label, country="United States", denomination="set", year_from=y0, year_to=y1, mint_marks=["S"],
        metal="Ag", fineness=None, gross_weight_g=None, pure_toz=pure.quantize(Q), per_face_unit=False, citation=SET_CITE,
    )


ROWS_V3 += [
    _set("us-set-quarters-states", "US 50 State Quarters silver proof set, 5 quarters 90% (1999–2008-S)", 1999, 2008, 5 * _Q90),
    _set("us-set-quarters-dc", "US DC and Territories quarters silver proof set, 6 quarters 90% (2009-S)", 2009, 2009, 6 * _Q90),
    _set("us-set-quarters-atb-90", "US America the Beautiful quarters silver proof set, 5 quarters 90% (2010–2018-S)", 2010, 2018, 5 * _Q90),
    _set("us-set-quarters-atb-999", "US America the Beautiful quarters silver proof set, 5 quarters .999 (2019–2020-S)", 2019, 2020, 5 * _Q999),
    _set("us-set-quarters-women", "US American Women quarters silver proof set, 5 quarters .999 (2022–2025-S)", 2022, 2025, 5 * _Q999),
    _set("us-set-silver-1992", "US Silver Proof Set: dime, quarter, half, 90% (1992–1998-S)", 1992, 1998, _D90 + _Q90 + _H90),
    _set("us-set-silver-1999", "US Silver Proof Set: dime, 5 quarters, half, 90% (1999–2008, 2010–2018-S)", 1999, 2018, _D90 + 5 * _Q90 + _H90),
    _set("us-set-silver-2009", "US Silver Proof Set: dime, 6 quarters, half, 90% (2009-S)", 2009, 2009, _D90 + 6 * _Q90 + _H90),
    _set("us-set-silver-999", "US Silver Proof Set: dime, 5 quarters, half, .999 (2019–2020, 2022–2025-S)", 2019, 2025, _D999 + 5 * _Q999 + _H999),
]
SILVER_ONLY_PREFIXES = ("us-silver-proof-", "us-bicentennial-", "us-set-")


# --- Version 4: the world catalogue (migration 0006) ----------------------------------------
# One JSON file per region in app/data/catalogue. Every row names the page its figures came from;
# rows we could not check against a source were left out rather than guessed.

CATALOGUE_DIR = Path(__file__).parent / "data" / "catalogue"
_COUNTRY_ALIASES = {"Great Britain": "United Kingdom", "UK": "United Kingdom", "England": "United Kingdom",
                    "USA": "United States", "US": "United States"}


def _catalogue_row(r: dict) -> dict:
    country = _COUNTRY_ALIASES.get(r["country"], r["country"])
    label = r["label"].strip()
    short = label[len(country):].strip() if label.lower().startswith(country.lower()) else label
    key = f"cat-{_slug(country)}-{_slug(short)}"[:120].rstrip("-")
    metal, fine = r["metal"], Decimal(str(r["fineness"])) if r.get("fineness") is not None else None
    gross = Decimal(str(r["gross_g"])) if r.get("gross_g") else None
    if r.get("pure_toz"):
        pure = Decimal(str(r["pure_toz"])).quantize(Q, rounding=ROUND_HALF_UP)
    else:
        pure = (gross / TROY * fine).quantize(Q, rounding=ROUND_HALF_UP)
    denom = r.get("denomination")
    if not denom or denom.startswith("("):
        denom = None
    note = (r.get("note") or "").strip()
    cite = r["source"] + (f". {note}" if note else "")
    return dict(
        key=key, label=label[:200], country=country, denomination=denom, year_from=r.get("year_from"),
        year_to=r.get("year_to"), mint_marks=None, metal=metal, fineness=fine, gross_weight_g=gross,
        pure_toz=pure, per_face_unit=False, citation=cite,
    )


def load_catalogue(files: list[str], directory: Path = CATALOGUE_DIR) -> list[dict]:
    rows: list[dict] = []
    for name in files:
        rows += [_catalogue_row(r) for r in json.loads((directory / name).read_text(encoding="utf-8"))]
    return rows


# Each migration loads a fixed list of files, so a file added later gets its own migration.
CATALOGUE_V4 = ["americas.json", "europe.json", "uk_commonwealth.json", "us_expanded.json", "world_bullion_asia.json"]
CATALOGUE_V5 = ["americas_2.json", "bullion_2.json", "europe_2.json"]
CATALOGUE_V6 = ["bullion_3.json"]
ROWS_V4 = load_catalogue(CATALOGUE_V4)
ROWS_V5 = load_catalogue(CATALOGUE_V5)
ROWS_V6 = load_catalogue(CATALOGUE_V6)

ROWS = ROWS_V1 + ROWS_V2 + ROWS_V3 + ROWS_V4 + ROWS_V5 + ROWS_V6
