"""Country names and denominations as people write them, reduced to forms that can be compared.

"Great Britain", "British" and "UK" all mean the United Kingdom of the reference table; "half crown",
"Half-Crown" and "1/2 crown" are one denomination; "5 Pesos" and "five peso" too.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

US = "United States"

# name or adjective (lower case) -> the country as the reference table spells it
COUNTRY_WORDS: dict[str, str] = {
    "united states": US, "usa": US, "u.s.a.": US, "u.s.": US, "us": US, "american": US, "america": US,
    "united kingdom": "United Kingdom", "great britain": "United Kingdom", "britain": "United Kingdom",
    "british": "United Kingdom", "england": "United Kingdom", "english": "United Kingdom", "uk": "United Kingdom",
    "gb": "United Kingdom", "scotland": "United Kingdom",
    "british india": "British India", "india": "British India",
    "canada": "Canada", "canadian": "Canada",
    "newfoundland": "Newfoundland",
    "mexico": "Mexico", "mexican": "Mexico", "mexicano": "Mexico", "estados unidos mexicanos": "Mexico",
    "australia": "Australia", "australian": "Australia",
    "new zealand": "New Zealand",
    "south africa": "South Africa", "south african": "South Africa", "suid afrika": "South Africa",
    "ireland": "Ireland", "irish": "Ireland", "eire": "Ireland",
    "austria": "Austria", "austrian": "Austria", "osterreich": "Austria",
    "china": "China", "chinese": "China",
    "hong kong": "Hong Kong",
    "straits settlements": "Straits Settlements",
    "japan": "Japan", "japanese": "Japan",
    "korea": "Korea", "korean": "Korea",
    "philippines": "Philippines", "philippine": "Philippines", "filipinas": "Philippines",
    "peru": "Peru", "peruvian": "Peru",
    "venezuela": "Venezuela", "venezuelan": "Venezuela",
    "cuba": "Cuba", "cuban": "Cuba",
    "panama": "Panama", "panamanian": "Panama",
    "guatemala": "Guatemala", "guatemalan": "Guatemala",
    "colombia": "Colombia", "colombian": "Colombia", "new granada": "Colombia",
    "iran": "Iran", "iranian": "Iran", "persia": "Iran", "persian": "Iran",
    "ottoman": "Ottoman Empire", "ottoman empire": "Ottoman Empire", "turkey": "Ottoman Empire",
    "saudi arabia": "Saudi Arabia", "saudi": "Saudi Arabia",
    "somalia": "Somalia", "somalian": "Somalia",
    "armenia": "Armenia", "armenian": "Armenia",
    "france": "France", "french": "France",
    "germany": "Germany", "german": "Germany", "deutschland": "Germany", "german empire": "Germany",
    "switzerland": "Switzerland", "swiss": "Switzerland", "helvetia": "Switzerland",
    "italy": "Italy", "italian": "Italy",
    "netherlands": "Netherlands", "dutch": "Netherlands", "holland": "Netherlands",
    "belgium": "Belgium", "belgian": "Belgium",
    "spain": "Spain", "spanish": "Spain",
    "portugal": "Portugal", "portuguese": "Portugal",
    "sweden": "Sweden", "swedish": "Sweden", "sveriges": "Sweden", "sverige": "Sweden",
    "norway": "Norway", "norwegian": "Norway",
    "denmark": "Denmark", "danish": "Denmark",
    "finland": "Finland", "finnish": "Finland",
    "russia": "Russia", "russian": "Russia",
    "hungary": "Hungary", "hungarian": "Hungary",
    "poland": "Poland", "polish": "Poland",
    "czechoslovakia": "Czechoslovakia",
    "greece": "Greece", "greek": "Greece",
}
# abbreviations that only count when written in capitals ("US", not "us")
_CAPS_ONLY = {"us", "uk", "gb", "usa"}
_COUNTRY_RE = re.compile(
    r"(?<![\w.])(" + "|".join(re.escape(w) for w in sorted(COUNTRY_WORDS, key=len, reverse=True)) + r")(?![\w])", re.I
)


def canonical_country(text: str | None) -> str | None:
    """The reference table's name for a country as typed ("UK" -> "United Kingdom"); unknown names pass through."""
    if not text or not text.strip():
        return None
    t = re.sub(r"\s+", " ", fold(text).strip().lower())
    return COUNTRY_WORDS.get(t, text.strip())


def find_country(text: str) -> str | None:
    """The first country named in free text, if any."""
    for m in _COUNTRY_RE.finditer(fold(text)):
        word = m.group(1)
        if word.lower() in _CAPS_ONLY and word != word.upper():
            continue
        return COUNTRY_WORDS[word.lower()]
    return None


# --- denominations ---------------------------------------------------------------------------

US_DENOMS: dict[str, tuple[str, ...]] = {
    "1c": ("1c", "cent", "1 cent", "penny", "one cent"),
    "3c": ("3c", "3 cents", "three cents", "three cent", "trime"),
    "5c": ("5c", "nickel", "5 cents", "$0.05", "five cents", "half dime", "half disme"),
    "10c": ("10c", "dime", "10 cents", "$0.10", "ten cents"),
    "20c": ("20c", "20 cents", "twenty cents", "twenty cent"),
    "25c": ("25c", "quarter", "25 cents", "$0.25", "quarter dollar"),
    "50c": ("50c", "half", "half dollar", "50 cents", "$0.50"),
    "$1": ("$1", "dollar", "1 dollar", "one dollar", "silver dollar"),
    "trade$1": ("trade dollar", "1 trade dollar"),
    "$2.50": ("$2.50", "$2.5", "quarter eagle", "2.5 dollars"),
    "$3": ("$3", "3 dollars", "three dollars", "three dollar"),
    "$4": ("$4", "stella", "4 dollars"),
    "$5": ("$5", "half eagle", "5 dollars", "five dollars"),
    "$10": ("$10", "eagle", "10 dollars", "ten dollars"),
    "$20": ("$20", "double eagle", "20 dollars", "twenty dollars"),
    "$50": ("$50", "50 dollars"),
    "$100": ("$100", "100 dollars"),
}
_US_EXACT = {a: code for code, aliases in US_DENOMS.items() for a in aliases}
_US_BY_LENGTH = sorted(((a, code) for a, code in _US_EXACT.items() if len(a) > 3), key=lambda ac: -len(ac[0]))


def us_denom(text: str | None) -> str | None:
    """US denomination code ("10c", "$1") for text such as "Dime" or "Half Dollar"."""
    if not text:
        return None
    t = re.sub(r"[\s-]+", " ", text.strip().lower())
    if t in _US_EXACT:
        return _US_EXACT[t]
    for alias, code in _US_BY_LENGTH:  # longest first, so "half dime" wins over "half"
        if re.search(rf"(?<![\w$]){re.escape(alias)}(?!\w)", t):
            return code
    return None


_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "eight": "8",
                 "ten": "10", "twenty": "20", "fifty": "50", "hundred": "100", "half": "1/2", "quarter": "1/4",
                 "tenth": "1/10", "double": "2"}
_PENCE = {"twopence": "2 penny", "threepence": "3 penny", "fourpence": "4 penny", "sixpence": "6 penny",
          "groat": "4 penny"}
_PLURALS = {"reales": "real", "reals": "real", "bolivares": "bolivar", "soles": "sol", "lire": "lira",
            "kroner": "krone", "kronor": "krona", "kronen": "krone", "pence": "penny", "pennies": "penny",
            "colones": "colon", "quetzales": "quetzal", "korun": "koruna", "zlotych": "zloty", "zlote": "zloty",
            "drachmai": "drachma", "drachmes": "drachma", "centesimi": "centesimo", "pfennige": "pfennig",
            "onzas": "onza", "coronas": "corona", "escudos": "escudo"}
_KEEP_S = ("ss", "us", "is")


def fold(text: str) -> str:
    """Strip accents: "Bolívares" -> "Bolivares", "Centésimos" -> "Centesimos"."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _num(token: str) -> str:
    try:
        if "/" in token:
            a, b = token.split("/")
            v = Decimal(a) / Decimal(b)
        else:
            v = Decimal(token)
    except (InvalidOperation, ZeroDivisionError, ValueError):
        return token
    s = format(v.normalize(), "f")
    return s


def denom_key(text: str | None) -> str | None:
    """A comparable form of any denomination: "Half Crown" -> "0.5 crown", "5 Pesos" -> "5 peso", "2½ pesos" -> "2.5 peso"."""
    if not text or not text.strip():
        return None
    t = text.replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4").replace("¢", " cent")
    t = fold(t).lower()
    t = re.sub(r"\(.*?\)", " ", t)  # "1 Yuan (7 Mace 2 Candareens)"
    t = re.sub(r"\$\s?(\d+(?:\.\d+)?)", r"\1 dollar", t)
    t = re.sub(r"(\d)\s?c\b", r"\1 cent", t)
    t = re.sub(r"half[\s-]?(crown|dollar|dime|eagle|rupee|anna|sovereign|penny|pound|real|peso|onza|azadi|balboa|krugerrand)",
               r"half \1", t)
    words = re.findall(r"\d+(?:\.\d+)?/\d+|\d+(?:\.\d+)?|[a-z]+", t)
    out: list[str] = []
    for w in words:
        if w in _PENCE:
            out += _PENCE[w].split()
            continue
        w = _NUMBER_WORDS.get(w, w)
        if w in _PLURALS:
            w = _PLURALS[w]
        elif re.fullmatch(r"[a-z]{4,}s", w) and not w.endswith(_KEEP_S):
            w = w[:-1]
        out.append(w)
    # numbers: "2 1/2" -> "2.5", then every number in plain decimal form
    merged: list[str] = []
    for w in out:
        if merged and "/" in w and re.fullmatch(r"\d+", merged[-1]):
            merged[-1] = _num(str(Decimal(merged[-1]) + Decimal(_num(w))))
        elif re.fullmatch(r"\d+(?:\.\d+)?(?:/\d+)?", w):
            merged.append(_num(w))
        else:
            merged.append(w)
    if not merged:
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?", merged[0]):
        merged.insert(0, "1")
    return " ".join(merged)


# foreign denominations as they appear in titles: an optional amount and a unit
FOREIGN_UNITS = (
    r"centavos?|centimos?|centesimos?|centimes?|pesos?|reales?|reals?|escudos?|francs?|francos?|reichsmarks?|marks?|"
    r"pfennigs?|kronen|kroner|kronor|krone|krona|coronas?|corona|lire|lira|guilders?|gulden|double\s*florins?|florins?|"
    r"zloty|zlotych|forint|korun|koruna|rubles?|roubles?|kopeks?|rupees?|annas?|yen|sen|yuan|jiao|chon|won|drams?|"
    r"pengo|korona|markkaa|markka|pennia|penni|reis|skilling|kopecks?|kurush|piastres?|rials?|riyals?|pahlavi|azadi|balboas?|bolivares|bolivar|soles|sol|libras?|quetzal(?:es)?|"
    r"colones|cordobas?|lempiras?|sucres?|shillings?|pence|sixpence|threepence|fourpence|twopence|groats?|"
    r"half[\s-]?crowns?|crowns?|guineas?|pounds?|euros?|drachmas?|dinars?|dirhams?|thalers?|talers?|ducats?|"
    r"kreuzer|heller|rand|onzas?|stotinki|leva|lei|bani|dinara|para|ore|øre|cents?|dollars?"
)
_AMOUNT = r"(?:\d+(?:\.\d+)?(?:\s?1/2|½)?|\d+/\d+|one|two|three|four|five|six|ten|twenty|fifty|hundred|half|quarter|double)"
FOREIGN_DENOM_RE = re.compile(rf"(?<![\w$])(?:({_AMOUNT})[\s-]?)?({FOREIGN_UNITS})(?!\w)", re.I)
_YEARISH = re.compile(r"1[5-9]\d\d|20\d\d")


def find_foreign_denomination(text: str) -> str | None:
    """The denomination named in a foreign coin's title ("50 Cents", "Half Crown", "2 1/2 Pesos"), if any."""
    for m in FOREIGN_DENOM_RE.finditer(fold(text.replace("½", " 1/2"))):
        amount, unit = m.group(1), m.group(2)
        if amount and _YEARISH.fullmatch(amount.strip()):
            amount = None  # "1964 pesos" is a date, not an amount
        if unit.lower() in ("cent", "cents", "dollar", "dollars", "pound", "pounds", "sen", "para", "sol", "won", "rand", "mark", "marks", "ore", "lei") and not amount:
            continue  # too common as plain words to count alone
        return f"{amount} {unit}".strip() if amount else unit
    return None
