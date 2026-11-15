"""Series checklists: which coins of a series you have, and which are missing. Coins inside mint sets count.

A coin is matched on its year, its mint mark where the series is collected by mint, its denomination, and the
design's name appearing in the item's title or series ("Oklahoma", "Morgan"). It's a help for spotting gaps,
not a census: an item recorded without a year or with an unusual title won't be counted.

Sources: quarter and dollar designs as in services/mint_sets. The Morgan, Peace and Franklin date-and-mint lists
are the regular business strikes of each series, written from general knowledge and checked only by their well
known totals (96, 24 and 35 coins).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Item
from app.services import mint_sets
from app.services.coin_words import us_denom


@dataclass(frozen=True)
class Entry:
    label: str
    year: int | None
    denom: str | None  # US code: 25c, 50c, $1
    words: tuple[str, ...] = ()  # each must appear in the item's text
    mint: str | None = None  # None: any mint; "" : Philadelphia (no mark, or P)
    group: str = ""


@dataclass
class Checklist:
    key: str
    name: str
    note: str
    entries: list[Entry] = field(default_factory=list)


@dataclass(frozen=True)
class Holding:
    item_id: int
    title: str  # the item's title (for a coin in a set, the set's)
    year: int | None
    mint: str
    denom: str | None
    text: str
    in_set: bool


def _plain(name: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", name).lower().replace("'", "'")


def _dated(series: str, denom: str, words: tuple[str, ...], years: dict[int, str]) -> list[Entry]:
    out = []
    for year, mints in years.items():
        for m in mints.split():
            out.append(Entry(f"{year}{'' if m == 'P' else '-' + m} {series}", year, denom, words, "" if m == "P" else m, str(year)))
    return out


def _span(a: int, b: int, mints: str) -> dict[int, str]:
    return {y: mints for y in range(a, b + 1)}


MORGAN = {1878: "P CC S", **_span(1879, 1885, "P CC O S"), **_span(1886, 1888, "P O S"), **_span(1889, 1893, "P CC O S"),
          **_span(1894, 1904, "P O S"), 1921: "P D S"}
PEACE = {1921: "P", 1922: "P D S", 1923: "P D S", 1924: "P S", 1925: "P S", 1926: "P D S", 1927: "P D S", 1928: "P S",
         1934: "P D S", 1935: "P S"}
FRANKLIN = {1948: "P D", 1949: "P D S", 1950: "P D", **_span(1951, 1954, "P D S"), 1955: "P", 1956: "P", **_span(1957, 1963, "P D")}


def _designs(name: str, table: dict[int, list[str]], denom: str, suffix: str) -> list[Entry]:
    return [Entry(f"{year} {n} {suffix}", year, denom, (_plain(n),), None, str(year)) for year, names in table.items() for n in names]


def all_checklists(this_year: int) -> list[Checklist]:
    return [
        Checklist("state-quarters", "50 State Quarters", "One of each design, any mint.",
                  _designs("state", mint_sets.STATE_QUARTERS, "25c", "quarter")),
        Checklist("territory-quarters", "DC and U.S. Territories Quarters", "The six 2009 designs, any mint.",
                  [Entry(f"2009 {n} quarter", 2009, "25c", (_plain(n),), None, "2009") for n in mint_sets.TERRITORY_QUARTERS]),
        Checklist("atb-quarters", "America the Beautiful Quarters", "One of each design 2010 to 2021, any mint.",
                  _designs("atb", {**mint_sets.ATB_QUARTERS, 2021: ["Tuskegee Airmen"]}, "25c", "quarter")),
        Checklist("women-quarters", "American Women Quarters", "One of each design 2022 to 2025, any mint.",
                  _designs("women", mint_sets.WOMEN_QUARTERS, "25c", "quarter")),
        Checklist("presidential-dollars", "Presidential Dollars", "One of each president 2007 to 2016, any mint.",
                  [Entry(f"{year} {n} dollar", year, "$1", (_plain(n).split()[-1],), None, str(year))
                   for year, names in mint_sets.PRESIDENTS.items() for n in names]),
        Checklist("morgan-dollars", "Morgan Dollars by date and mint", "The 96 regular issues, 1878 to 1904 and 1921.",
                  _dated("Morgan dollar", "$1", ("morgan",), MORGAN)),
        Checklist("peace-dollars", "Peace Dollars by date and mint", "The 24 regular issues, 1921 to 1935.",
                  _dated("Peace dollar", "$1", ("peace",), PEACE)),
        Checklist("franklin-halves", "Franklin Half Dollars by date and mint", "The 35 regular issues, 1948 to 1963.",
                  _dated("Franklin half dollar", "50c", ("franklin",), FRANKLIN)),
        Checklist("silver-eagles", "American Silver Eagles by year", "One for each year from 1986.",
                  [Entry(f"{y} American Silver Eagle", y, None, ("silver eagle",), None, f"{y // 10 * 10}s") for y in range(1986, this_year + 1)]),
    ]


def _mint(m: str | None) -> str:
    m = (m or "").strip().upper()
    return "" if m == "P" else m


def holdings(db: Session, owner_id: int) -> list[Holding]:
    """Every coin held: coin and bullion items, and each coin listed inside a set. Sold and deleted items are left out."""
    out: list[Holding] = []
    items = db.scalars(
        select(Item).where(Item.owner_id == owner_id, Item.deleted_at.is_(None), Item.status != "sold",
                           Item.item_type.in_(("coin", "bullion", "set")))
        .options(selectinload(Item.coin), selectinload(Item.set_coins))
    )
    for it in items:
        if it.item_type == "set":
            for c in it.set_coins:
                out.append(Holding(it.id, it.title, c.year, _mint(c.mint_mark), us_denom(c.denomination),
                                   f"{c.label} {c.series or ''}".lower(), True))
        elif it.coin is not None:
            c = it.coin
            text = " ".join(x for x in (it.title, c.series, c.product_line, c.variety_notes) if x).lower()
            out.append(Holding(it.id, it.title, c.year, _mint(c.mint_mark), us_denom(c.denomination) or us_denom(c.series), text, False))
    return out


def matches(e: Entry, h: Holding) -> bool:
    if e.year is not None and h.year != e.year:
        return False
    if e.mint is not None and h.mint != e.mint:
        return False
    if e.denom and h.denom and h.denom != e.denom:
        return False
    return all(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", h.text) for w in e.words)


def progress(checklist: Checklist, held: list[Holding]) -> list[tuple[Entry, list[Holding]]]:
    rows = []
    for e in checklist.entries:
        seen: dict[int, Holding] = {}
        for h in held:
            if h.item_id not in seen and matches(e, h):
                seen[h.item_id] = h
        rows.append((e, list(seen.values())))
    return rows
