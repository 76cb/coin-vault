"""Read a listing title or a short description and fill in what it says.

"2021 $1 Silver Eagle T2 First Production PCGS MS70" -> bullion coin, United States, 2021, $1,
American Silver Eagle (1 oz silver), slabbed PCGS MS70, designations First Production, Type 2.

Only facts written in the text are taken; nothing is looked up or guessed. The caller shows the
result as a filled-in form the owner checks before saving.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.services.coin_words import US, find_country, find_foreign_denomination

GRADERS = ["PCGS", "NGC", "ANACS", "ICG", "CACG", "SEGS", "PMG", "PCI"]
GRADE_RE = re.compile(r"\b(MS|PR|PF|SP|AU|XF|EF|VF|VG|AG|FR|PO|F|G)[\s-]?(\d{1,2})(\+)?(?![\d/])", re.I)

# (pattern, designation as written on the label)
DESIGNATIONS: list[tuple[str, str]] = [
    (r"\bultra\s*cameo\b|(?<![a-z])ucam\b", "UCAM"),
    (r"\bdeep\s*cameo\b|(?<![a-z])dcam\b", "DCAM"),
    (r"(?<![a-z])dmpl\b|\bdeep\s*mirror\s*proof\s*like\b", "DMPL"),
    (r"\bfirst\s*day\s*of\s*issue\b|\bfdoi\b|\bfdi\b", "First Day of Issue"),
    (r"\bfirst\s*prod(?:uction|\.)?(?![a-z])", "First Production"),
    (r"\bfirst\s*strike\b", "First Strike"),
    (r"\bfirst\s*releases?\b", "First Releases"),
    (r"\bearly\s*releases?\b", "Early Releases"),
    (r"\badvanced?\s*releases?\b", "Advanced Releases"),
    (r"\blast\s*day\s*(?:of\s*)?prod(?:uction|\.)?(?![a-z])", "Last Day of Production"),
    (r"\breverse\s*proof\b", "Reverse Proof"),
    (r"\benhanced\b", "Enhanced"),
    (r"\bburnished\b", "Burnished"),
    (r"\bfull\s*bell\s*lines\b|\bfbl\b", "FBL"),
    (r"\bfull\s*bands\b|\bfb\b", "FB"),
    (r"\bfull\s*steps\b|\bfs\b", "FS"),
    (r"\bfull\s*head\b|\bfh\b", "FH"),
    (r"\bcac\b", "CAC"),
    (r"(?<!deep )(?<!ultra )\bcameo\b", "Cameo"),
    (r"(?<![a-z])(?<!dm)pl\b|\bproof\s*like\b|\bprooflike\b", "PL"),
    (r"\bdetails\b", "Details"),
]

LABELS = [  # (pattern, name) of holder labels; kept in notes so the title can stay as the seller wrote it
    (r"legends\s*(?:of\s*)?life", "Legends of Life"), (r"flag\s*label", "Flag Label"), (r"\bmercanti\b", "Mercanti signed"),
    (r"\bmoy\b", "Moy signed"), (r"\bcleveland\b", "Cleveland"), (r"\bsinnock\b", "Sinnock"), (r"liberty\s*bell", "Liberty Bell"),
    (r"eagle\s*label", "Eagle Label"), (r"blue\s*label", "Blue Label"), (r"gold\s*foil", "Gold Foil"),
    (r"hand\s*signed|\bsigned\b", "Signed"),
]

REFINERS = [
    "Valcambi", "PAMP Suisse", "PAMP", "Argor-Heraeus", "Heraeus", "Metalor", "Credit Suisse", "UBS", "Perth Mint",
    "Royal Canadian Mint", "RCM", "Royal Mint", "Engelhard", "Johnson Matthey", "Sunshine Minting", "Sunshine",
    "Asahi", "Scottsdale", "Geiger", "Umicore", "Elemetal", "Golden State Mint", "Highland Mint", "SilverTowne",
]

# US series -> denomination code used by the reference table
US_SERIES: list[tuple[str, str, str]] = [  # (pattern, series name, denomination)
    (r"\bmorgan\b", "Morgan", "$1"),
    (r"\bpeace\s*dollar\b|\bpeace\b(?=.*\bdollar\b)", "Peace", "$1"),
    (r"\beisenhower\b|\bike\s*dollar\b", "Eisenhower", "$1"),
    (r"\bwalking\s*liberty\s*half\b|\bwalker\b", "Walking Liberty", "50c"),
    (r"\bfranklin\b", "Franklin", "50c"),
    (r"\bkennedy\b", "Kennedy", "50c"),
    (r"\bstanding\s*liberty\b", "Standing Liberty", "25c"),
    (r"\bwashington\s*quarter\b", "Washington", "25c"),
    (r"\bamerica\s*the\s*beautiful\b|\batb\b|\bnational\s*park\b|\bnp\b", "America the Beautiful", "25c"),
    (r"\bstate\s*quarter\b|\b50\s*states?\b", "50 State Quarters", "25c"),
    (r"\bamerican\s*women\b", "American Women", "25c"),
    (r"\bbicentennial\b|\b1776[-\s]1976\b", "Bicentennial", None),
    (r"\bmercury\b|\bwinged\s*liberty\b", "Mercury", "10c"),
    (r"\broosevelt\b", "Roosevelt", "10c"),
    (r"\bwar\s*nickel\b|\bjefferson\b", "Jefferson", "5c"),
    (r"\bbuffalo\s*nickel\b|\bindian\s*head\s*nickel\b", "Buffalo", "5c"),
    (r"\bbarber\s*half\b", "Barber", "50c"),
    (r"\bbarber\s*quarter\b", "Barber", "25c"),
    (r"\bbarber\s*dime\b", "Barber", "10c"),
    (r"\bsaint[\s-]*gaudens\b|\bst\.?\s*gaudens\b|\bdouble\s*eagle\b", "Saint-Gaudens", "$20"),
]

# US series by denomination and year, for a title that names only the denomination ("1956 Quarter").
# Years where two designs overlap (1909 cents, 1921 dollars, 1938 nickels, 1975-76 Bicentennials) are left out.
US_SERIES_BY_YEAR: dict[str, list[tuple[int, int, str]]] = {
    "1c": [(1859, 1908, "Indian Head"), (1910, 1958, "Lincoln Wheat"), (1959, 2008, "Lincoln Memorial"), (2010, 2099, "Lincoln Shield")],
    "5c": [(1913, 1937, "Buffalo"), (1939, 2099, "Jefferson")],
    "10c": [(1892, 1915, "Barber"), (1917, 1945, "Mercury"), (1946, 2099, "Roosevelt")],
    "25c": [(1892, 1915, "Barber"), (1917, 1930, "Standing Liberty"), (1932, 1974, "Washington"), (1977, 1998, "Washington"),
            (1999, 2008, "50 State Quarters"), (2010, 2021, "America the Beautiful"), (2022, 2025, "American Women")],
    "50c": [(1892, 1915, "Barber"), (1917, 1947, "Walking Liberty"), (1948, 1963, "Franklin"), (1964, 1974, "Kennedy"), (1977, 2099, "Kennedy")],
    "$1": [(1878, 1904, "Morgan"), (1922, 1935, "Peace"), (1971, 1974, "Eisenhower"), (1977, 1978, "Eisenhower"), (1979, 1981, "Susan B. Anthony")],
}


def us_series_for(denomination: str | None, year: int | None) -> str | None:
    for y0, y1, name in US_SERIES_BY_YEAR.get(denomination or "", []):
        if year and y0 <= year <= y1:
            return name
    return None


# Bullion programmes -> (product line, country, default metal, {metal or size: reference key})
BULLION: list[tuple[str, str, str, str]] = [
    (r"\bsilver\s*eagle\b", "American Silver Eagle", "United States", "Ag"),
    (r"\bgold\s*eagle\b", "American Gold Eagle", "United States", "Au"),
    (r"\bplatinum\s*eagle\b", "American Platinum Eagle", "United States", "Pt"),
    (r"\bpalladium\s*eagle\b", "American Palladium Eagle", "United States", "Pd"),
    (r"\bgold\s*buffalo\b|\bbuffalo\b(?!\s*nickel)", "American Gold Buffalo", "United States", "Au"),
    (r"\bmaple\s*leaf\b|\bmaple\b|\bsml\b|\bgml\b", "Maple Leaf", "Canada", "Ag"),
    (r"\bbritannia\b", "Britannia", "United Kingdom", "Ag"),
    (r"\bphilharmonic\b|\bphilharmoniker\b", "Philharmonic", "Austria", "Ag"),
    (r"\blibertad\b", "Libertad", "Mexico", "Ag"),
    (r"\bkangaroo\b", "Kangaroo", "Australia", "Au"),
    (r"\bkookaburra\b", "Kookaburra", "Australia", "Ag"),
    (r"\bkoala\b", "Koala", "Australia", "Ag"),
    (r"\blunar\b|\byear\s+of\s+the\s+(?:rat|mouse|ox|tiger|rabbit|hare|dragon|snake|horse|goat|sheep|ram|monkey|rooster|dog|pig)\b",
     "Lunar series", "Australia", "Ag"),
    (r"\bpanda\b", "Panda", "China", "Ag"),
    (r"\bkrugerrand\b", "Krugerrand", "South Africa", "Au"),
    (r"\bsovereign\b", "Sovereign", "United Kingdom", "Au"),
    (r"\b100\s*corona\b|\b100\s*kronen\b", "100 Corona", "Austria", "Au"),
    (r"\bqueen'?s\s*beasts?\b", "Queen's Beasts", "United Kingdom", "Ag"),
    (r"\btudor\s*beasts?\b", "Tudor Beasts", "United Kingdom", "Ag"),
    (r"\bnoah'?s\s*ark\b", "Noah's Ark", "Armenia", "Ag"),
    (r"\bsomali(?:a|an)?\s*elephant\b", "Somalian Elephant", "Somalia", "Ag"),
    (r"\bplatypus\b", "Platypus", "Australia", "Pt"),
    (r"\bswan\b", "Swan", "Australia", "Ag"),
    (r"\b(?:bahar\s*)?azadi\b", "Bahar Azadi", "Iran", "Au"),
    (r"\bcanadian\s*wildlife\b", "Wildlife series", "Canada", "Ag"),
]
# the word a reference label must contain to be that product line ("Lunar series" -> "lunar")
LINE_WORDS = {"Maple Leaf": "maple", "Lunar series": "lunar", "Queen's Beasts": "queen", "Tudor Beasts": "tudor",
              "Noah's Ark": "noah", "Somalian Elephant": "elephant", "Bahar Azadi": "azadi", "Wildlife series": "wildlife",
              "100 Corona": "corona"}
GOLD_EAGLE_SIZES = {"$50": "age-1oz", "$25": "age-half", "$10": "age-quarter", "$5": "age-tenth",
                    "1": "age-1oz", "1/2": "age-half", "1/4": "age-quarter", "1/10": "age-tenth"}
DIRECT_KEYS = {
    ("American Silver Eagle", "Ag"): "ase-1oz",
    ("American Gold Buffalo", "Au"): "buffalo-au-1oz",
    ("American Platinum Eagle", "Pt"): "ape-1oz",
    ("Maple Leaf", "Ag"): "maple-ag-1oz", ("Maple Leaf", "Au"): "maple-au-1oz",
    ("Maple Leaf", "Pt"): "maple-pt-1oz", ("Maple Leaf", "Pd"): "maple-pd-1oz",
    ("Britannia", "Ag"): "britannia-ag-1oz", ("Britannia", "Au"): "britannia-au-1oz",
    ("Philharmonic", "Ag"): "philharmonic-ag-1oz", ("Philharmonic", "Au"): "philharmonic-au-1oz",
    ("Libertad", "Ag"): "libertad-ag-1oz", ("Kangaroo", "Ag"): "kangaroo-ag-1oz", ("Panda", "Ag"): "panda-ag-30g",
    ("Krugerrand", "Au"): "krugerrand-1oz",
    ("Kookaburra", "Ag"): "kookaburra-ag-1oz", ("Kangaroo", "Au"): "kangaroo-au-1oz",
    ("American Palladium Eagle", "Pd"): "ape-pd-1oz",
}
GOLD_MAPLE_SIZES = {"1": "maple-au-1oz", "1/2": "maple-au-half", "1/4": "maple-au-quarter", "1/10": "maple-au-tenth", "1/20": "maple-au-twentieth"}

METAL_WORDS = {"gold": "Au", "silver": "Ag", "platinum": "Pt", "palladium": "Pd"}
# chemical symbols as written on coins and labels ("1oz 9999 Ag", "Pt $15"), matched in this exact case
METAL_SYMBOLS = re.compile(r"(?<![A-Za-z])(Au|Ag|Pt|Pd)(?![A-Za-z])")
# NGC labels put the metal before the dollar sign: G$5 gold, S$1 silver, P$15 platinum
METAL_DOLLAR = re.compile(r"(?<![A-Za-z])(G|S|P|Pt|Pd)\$(?=\s?\d)")
METAL_DOLLAR_CODES = {"G": "Au", "S": "Ag", "P": "Pt", "Pt": "Pt", "Pd": "Pd"}
DENOM_RE = re.compile(
    r"(?<![\w.])\$\s?(\d+(?:\.\d{2})?)(?!\s*(?:face|fv))\b|\b(\d{1,2})\s?c(?:ents?)?\b|"
    r"\b(half\s*dollar|quarter\s*dollar|dime|quarter|nickel|cent|penny|dollar)\b",
    re.I,
)
WORD_DENOMS = {"half dollar": "50c", "quarter dollar": "25c", "dime": "10c", "quarter": "25c", "nickel": "5c",
               "cent": "1c", "penny": "1c", "dollar": "$1"}
SIZE_RE = re.compile(r"\b(\d+/\d+|\d+(?:\.\d+)?)\s?(troy\s*oz|ozt|oz|ounces?|kilos?|kg|grams?|gr|g)\b", re.I)
BANKNOTE_RE = re.compile(r"\b(silver\s*certificate|gold\s*certificate|federal\s*reserve\s*note|frn|legal\s*tender|"
                         r"national\s*bank\s*note|banknote|bank\s*note|pmg|fr\.?\s?\d{3,4})\b", re.I)
LOT_RE = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s*(?:face|fv)\b|\bjunk\s*silver\b", re.I)
QTY_RE = re.compile(r"\b(?:lot\s*of|roll\s*of|qty:?|quantity:?)\s*(\d{1,4})\b|\b(\d{1,4})\s*(?:pcs|pieces|coins)\b", re.I)


@dataclass
class Described:
    item_type: str = "coin"
    title: str = ""
    quantity: int = 1
    metal: str | None = None
    details: dict = field(default_factory=dict)
    condition: dict | None = None
    composition_key: str | None = None  # a specific reference row, when the text names one
    notes: list[str] = field(default_factory=list)
    recognized: list[str] = field(default_factory=list)  # plain-language list of what was understood
    size_toz: Decimal | None = None  # bullion size in troy ounces, when the text gives one


def _plain(v: Decimal) -> str:
    """Decimal without exponent or trailing zeros: 100, 2.5."""
    t = f"{v:f}"
    return t.rstrip("0").rstrip(".") if "." in t else t


def _size_g(amount: str, unit: str) -> tuple[Decimal, str, str]:
    """Return (grams, value as written, unit for bar details)."""
    if "/" in amount:
        a, b = amount.split("/")
        qty = Decimal(a) / Decimal(b)
    else:
        qty = Decimal(amount)
    u = unit.lower().replace(" ", "")
    if u.startswith(("oz", "troyoz", "ounce")) or u == "ozt":
        return qty * Decimal("31.1034768"), amount, "ozt"
    if u.startswith(("kg", "kilo")):
        return qty * 1000, amount, "kg"
    return qty, amount, "g"


def describe(text: str) -> Described:
    raw = re.sub(r"\s+", " ", text or "").strip()
    d = Described(title=raw[:300])
    if not raw:
        return d
    # "G$5" (NGC's gold $5): note the metal, and read the rest as an ordinary "$5"
    md = METAL_DOLLAR.search(raw)
    if md:
        d.metal = METAL_DOLLAR_CODES[md.group(1)]
        raw = METAL_DOLLAR.sub(" $", raw).replace("  ", " ")
    low = raw.lower()

    # --- metal and size ---
    for word, metal in METAL_WORDS.items():
        if d.metal is None and re.search(rf"\b{word}\b", low):
            d.metal = metal
            break
    if d.metal is None and (sym := METAL_SYMBOLS.search(raw)):
        d.metal = sym.group(1)
    size = SIZE_RE.search(raw)
    # "100x 1 gram" is a CombiBar-style multi-piece bar: 100 x 1 g = 100 g
    multi = re.search(r"\b(\d{1,3})\s?x\s?(\d+(?:\.\d+)?)\s?(g|gram|grams|oz)\b", raw, re.I)

    # --- grading ---
    grader = next((g for g in GRADERS if re.search(rf"\b{g}\b", raw, re.I)), None)
    grade = GRADE_RE.search(raw)
    designations = []
    for pat, name in DESIGNATIONS:
        if re.search(pat, low) and name not in designations:
            designations.append(name)
    if grader == "PMG":
        pass  # banknote grader; handled below
    sheldon = None
    grade_text = None
    if grade and 1 <= int(grade.group(2)) <= 70:
        sheldon = int(grade.group(2))
        grade_text = f"{grade.group(1).upper()}{grade.group(2)}{grade.group(3) or ''}"
    if grader or grade_text:
        slabbed = grader is not None and grader != "PMG"
        d.condition = {
            "grading": "slabbed" if slabbed else "raw",
            "grading_service": grader if slabbed else None,
            "grade_text": grade_text,
            "sheldon_grade": sheldon,
            "designations": [x for x in designations if x != "Details"],
            "details_reason": "Details grade" if "Details" in designations else None,
        }
        d.recognized.append(" ".join(x for x in [grader, grade_text] if x) + (f", {', '.join(d.condition['designations'])}" if d.condition["designations"] else ""))
    elif designations:
        d.notes.append("Designations: " + ", ".join(designations))

    labels = [name for pat, name in LABELS if re.search(pat, low)]
    if labels:
        d.notes.append("Label: " + ", ".join(labels))
    m = re.search(r"\b(?:T|Type)\s?([12])\b", raw)
    if m:
        d.details["variety_notes"] = f"Type {m.group(1)}"
        d.recognized.append(f"Type {m.group(1)}")

    # --- year and mint mark ---
    ym = re.search(r"\b(1[6-9]\d\d|20\d\d)(?:[-\s]?(CC|[PDSOWC])\b(?![-']))?", raw)
    if ym:
        d.details["year"] = int(ym.group(1))
        if ym.group(2):
            d.details["mint_mark"] = ym.group(2)
        d.recognized.append(f"{ym.group(1)}{'-' + ym.group(2) if ym.group(2) else ''}")

    # --- quantity ---
    q = QTY_RE.search(raw)
    if q:
        d.quantity = max(1, int(q.group(1) or q.group(2)))
        d.recognized.append(f"quantity {d.quantity}")

    # --- what kind of thing ---
    if BANKNOTE_RE.search(raw):
        d.item_type = "banknote"
        d.metal = None  # "silver certificate" names the note, not a metal content
        pmg = re.search(r"\bPMG\s*(?:[A-Za-z ]{0,20}?)\s*(\d{1,2})\s*(EPQ|PPQ|NET)?\b", raw, re.I)
        if pmg and 1 <= int(pmg.group(1)) <= 70:
            d.condition = {
                "grading": "slabbed", "grading_service": "PMG", "grade_text": " ".join(x for x in [pmg.group(1), (pmg.group(2) or "").upper()] if x),
                "sheldon_grade": int(pmg.group(1)), "designations": [x for x in [(pmg.group(2) or "").upper()] if x],
                "details_reason": None,
            }
            d.recognized = [r for r in d.recognized if r != "PMG"] + [f"PMG {d.condition['grade_text']}"]
        if "year" in d.details:  # notes carry a series year, not a date
            d.details["series"] = str(d.details.pop("year"))
        if grader == "PMG" or (d.condition and grader is None):
            if d.condition:
                d.condition["grading"] = "slabbed" if grader == "PMG" else "raw"
                d.condition["grading_service"] = "PMG" if grader == "PMG" else None
        dn = DENOM_RE.search(raw)
        if dn and dn.group(1):
            d.details["denomination"] = f"${dn.group(1)}"
        series = re.search(r"\bseries\s*(?:of\s*)?(\d{4}[A-Z]?)\b", raw, re.I)
        if series:
            d.details["series"] = series.group(1)
        d.details["country"] = "United States" if re.search(r"certificate|federal reserve|legal tender|national bank", low) else None
        d.recognized.insert(0, "banknote")
        return _clean(d)

    # a US silver proof set: the composition is the whole set's silver
    if re.search(r"\bsilver\s*proof\s*set\b", low) and d.details.get("year"):
        y = d.details["year"]
        quarters_only = bool(re.search(r"\bquarters?\b", low))
        key = _proof_set_key(y, quarters_only)
        d.item_type = "coin"
        d.metal = "Ag"
        d.details["country"] = "United States"
        d.details["series"] = "Silver Proof Set" if not quarters_only else "Quarters Silver Proof Set"
        d.details["denomination"] = "set"
        d.composition_key = key
        if re.search(r"\b(box|ogp|coa|certificate\s*of\s*authenticity)\b", low):
            d.notes.append("Original government packaging with certificate")
        d.recognized.insert(0, f"{y}-S {d.details['series'].lower()}")
        return _clean(d)

    lot = LOT_RE.search(raw)
    if lot and lot.group(1):
        d.item_type = "lot"
        d.details["face_value"] = lot.group(1)
        d.details["face_currency"] = "USD"
        pct = re.search(r"\b(90|40|35)\s?%", raw)
        d.composition_key = {"90": "us-90-per-face", "40": "us-40-half-per-face", "35": "us-war-nickel-per-face"}.get(
            pct.group(1) if pct else "90")
        d.recognized.insert(0, f"lot, ${lot.group(1)} face")
        return _clean(d)

    refiner = next((r for r in REFINERS if re.search(rf"\b{re.escape(r)}\b", raw, re.I)), None)
    is_bar = bool(re.search(r"\b(bar|bars|ingot|combibar|cast|minted\s*bar)\b", low)) or (refiner and not re.search(r"\bcoin|round\b", low))

    bullion = None
    # the abbreviations only count in capitals: "ASE", not "base"; "AGE", not "age"
    if re.search(r"\bASE\b", raw):
        bullion = ("American Silver Eagle", "United States", "Ag")
    elif re.search(r"\bAGE\b", raw):
        bullion = ("American Gold Eagle", "United States", "Au")
    for pat, line, country, default_metal in ([] if bullion else BULLION):
        if re.search(pat, low) and not (line == "American Gold Buffalo" and re.search(r"buffalo\s*nickel", low)):
            bullion = (line, country, default_metal)
            break

    if is_bar and not bullion:
        d.item_type = "bar"
        canonical = {"PAMP": "PAMP Suisse", "RCM": "Royal Canadian Mint", "Sunshine": "Sunshine Minting"}
        if refiner:
            d.details["refiner"] = canonical.get(refiner, refiner)
        if multi:
            grams, _, _ = _size_g(multi.group(2), multi.group(3))
            total = grams * int(multi.group(1))
            d.details["weight_value"] = _plain(total)
            d.details["weight_unit"] = "g"
        elif size:
            _, amount, unit = _size_g(size.group(1), size.group(2))
            d.details["weight_value"] = amount
            d.details["weight_unit"] = unit
        d.recognized.insert(0, " ".join(x for x in [d.details.get("refiner"), {"Au": "gold", "Ag": "silver", "Pt": "platinum", "Pd": "palladium"}.get(d.metal or "", ""), "bar"] if x)
                            + (f", {d.details['weight_value']} {d.details['weight_unit']}" if d.details.get("weight_value") else ""))
        if re.search(r"\bassay\b", low):
            d.details["has_assay_card"] = True
        return _clean(d)

    if bullion:
        line, country, default_metal = bullion
        metal = d.metal or default_metal
        if line == "American Gold Eagle" and re.search(r"\bsilver\s*eagle\b", low):
            line, metal = "American Silver Eagle", "Ag"
        d.item_type = "bullion"
        d.metal = metal
        word = {"Au": "Gold", "Ag": "Silver", "Pt": "Platinum", "Pd": "Palladium"}[metal]
        generic = ("Maple Leaf", "Britannia", "Philharmonic", "Libertad", "Kangaroo", "Panda", "Krugerrand", "Kookaburra", "Koala",
                   "Lunar series", "Queen's Beasts", "Tudor Beasts", "Noah's Ark", "Somalian Elephant", "Swan", "Platypus", "Wildlife series")
        d.details["product_line"] = f"{word} {line}" if line in generic else line
        # several mints strike Lunar coins: a country named in the title wins
        d.details["country"] = (find_country(raw) or country) if line == "Lunar series" else country
        dn = DENOM_RE.search(raw)
        if dn and dn.group(1):
            d.details["denomination"] = f"${dn.group(1)}"
        frac = re.search(r"\b(1/2|1/4|1/10|1/20|1)\s?(?:troy\s*)?oz\b", low)
        if size:
            grams, _, _ = _size_g(size.group(1), size.group(2))
            d.size_toz = grams / Decimal("31.1034768")
        if line == "American Gold Eagle":
            d.composition_key = GOLD_EAGLE_SIZES.get(frac.group(1) if frac else "") or GOLD_EAGLE_SIZES.get(d.details.get("denomination", ""), "age-1oz")
        elif line == "Maple Leaf" and metal == "Au":
            d.composition_key = GOLD_MAPLE_SIZES.get(frac.group(1) if frac else "1")
        elif line == "Sovereign":
            d.composition_key = ("sovereign-half" if re.search(r"\bhalf\b|1/2", low) else "sovereign-quarter" if re.search(r"\bquarter\b|1/4", low)
                                 else "sovereign-double" if re.search(r"\bdouble\b", low) else "sovereign-full")
        elif line == "100 Corona":
            d.composition_key = "corona-100-au"
        else:
            is_one_oz = not frac or frac.group(1) == "1"
            if is_one_oz or line == "Panda":
                d.composition_key = DIRECT_KEYS.get((line, metal))
        d.recognized.insert(0, d.details["product_line"])
        return _clean(d)

    # a regular coin
    d.item_type = "coin" if (ym or DENOM_RE.search(raw) or grade_text) else "other"
    named = find_country(raw)
    # "Mercury", "Liberty" and others are US series names, but not on a coin the title says is Belgian
    for pat, series, denom in ([] if named not in (None, US) else US_SERIES):
        if re.search(pat, low):
            d.details["series"] = series
            if denom:
                d.details["denomination"] = denom
            d.details["country"] = "United States"
            d.recognized.insert(0, f"{series} {denom or ''}".strip())
            break
    # a foreign coin: the country named in the title, and its denomination as written ("Half Crown", "5 Pesos")
    if "country" not in d.details and named and named != US:
        d.details["country"] = named
    foreign = d.details.get("country") not in (None, US)
    fd = find_foreign_denomination(raw) if "series" not in d.details else None
    if foreign and fd:
        d.details["denomination"] = fd
    if "denomination" not in d.details:
        dn = DENOM_RE.search(raw)
        if dn:
            if dn.group(1):
                d.details["denomination"] = f"${dn.group(1)}"
            elif dn.group(2):
                d.details["denomination"] = f"{dn.group(2)}c"
            elif dn.group(3):
                d.details["denomination"] = WORD_DENOMS[re.sub(r"\s+", " ", dn.group(3).lower())]
        elif fd:
            d.details["denomination"] = fd
    if d.item_type == "other" and fd:
        d.item_type = "coin"
    # "1956 Quarter": a US denomination and no other country named is a US coin, and its year says which design
    if not foreign and named in (None, US) and d.details.get("denomination") in US_SERIES_BY_YEAR and d.item_type == "coin":
        d.details["country"] = "United States"
        if "series" not in d.details:
            series = us_series_for(d.details["denomination"], d.details.get("year"))
            if series:
                d.details["series"] = series
                d.recognized.insert(0, f"{series} {d.details['denomination']}")
    if foreign:
        d.recognized.insert(0, " ".join(x for x in (d.details["country"], d.details.get("denomination")) if x))
    if d.item_type == "coin" and d.metal == "Ag" and re.search(r"\bproof\b|\bpr\s?\d|\bpf\s?\d", low) and d.details.get("year", 0) >= 1992:
        d.recognized.append("silver proof")
    if re.search(r"\b(us|u\.s\.|usa|united\s*states|american)\b", low) and "country" not in d.details:
        d.details["country"] = "United States"
    return _clean(d)


def _proof_set_key(year: int, quarters_only: bool) -> str | None:
    if quarters_only:
        for y0, y1, key in ((1999, 2008, "us-set-quarters-states"), (2009, 2009, "us-set-quarters-dc"),
                            (2010, 2018, "us-set-quarters-atb-90"), (2019, 2020, "us-set-quarters-atb-999"),
                            (2022, 2025, "us-set-quarters-women")):
            if y0 <= year <= y1:
                return key
        return None
    if 1992 <= year <= 1998:
        return "us-set-silver-1992"
    if year == 2009:
        return "us-set-silver-2009"
    if 1999 <= year <= 2018:
        return "us-set-silver-1999"
    if 2019 <= year <= 2025 and year != 2021:
        return "us-set-silver-999"
    return None


def _clean(d: Described) -> Described:
    d.details = {k: v for k, v in d.details.items() if v not in (None, "")}
    d.recognized = [r for r in d.recognized if r]
    return d
