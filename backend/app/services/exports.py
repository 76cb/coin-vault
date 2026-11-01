"""CSV export and the insurance report: the collection written out for spreadsheets, insurers and appraisers."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Item
from app.services import valuation
from app.services.items import _grade_label, cost_basis, photo_urls

ZERO = Decimal(0)
METAL_NAMES = {"Au": "gold", "Ag": "silver", "Pt": "platinum", "Pd": "palladium"}
KIND_LABELS = {"coin": "Coin", "bullion": "Bullion", "bar": "Bar", "banknote": "Banknote", "goldback": "Goldback", "lot": "Junk silver lot", "other": "Other"}
STATUS_LABELS = {"owned": "Owned", "for_sale": "For sale", "sold": "Sold"}


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def describe(item: Item) -> str:
    """One line from the item's details, e.g. "1881-S United States Dollar, Morgan Dollar"."""
    t = item.item_type
    if t in ("coin", "bullion") and item.coin:
        c = item.coin
        year = f"{c.year}{'-' + c.mint_mark if c.mint_mark else ''}" if c.year else _s(c.mint_mark)
        head = " ".join(x for x in (year, _s(c.country), _s(c.denomination)) if x)
        tail = ", ".join(x for x in (_s(c.series), _s(c.product_line)) if x and x.lower() not in head.lower())
        return ", ".join(x for x in (head, tail) if x)
    if t == "bar" and item.bar:
        b = item.bar
        weight = f"{b.weight_value.normalize():f} {b.weight_unit}" if b.weight_value is not None else ""
        return ", ".join(x for x in (weight, _s(b.refiner)) if x)
    if t == "banknote" and item.banknote:
        n = item.banknote
        return ", ".join(x for x in (" ".join(x for x in (_s(n.country), _s(n.denomination)) if x), _s(n.series)) if x)
    if t == "goldback" and item.goldback:
        from app.services.goldbacks import denomination_label

        g = item.goldback
        name = " ".join(x for x in (_s(g.state), "Goldback", denomination_label(g.denomination)) if x)
        return ", ".join(x for x in (name, str(g.year) if g.year else "", _s(g.variety)) if x)
    if t == "lot" and item.lot and item.lot.face_value is not None:
        return f"{item.lot.face_value:.2f} {item.lot.face_currency} face value"
    if t == "other" and item.other and item.other.attributes:
        return ", ".join(f"{k}: {v}" for k, v in item.other.attributes.items() if v not in (None, ""))
    return ""


def identifiers(item: Item) -> list[str]:
    """Numbers an insurer can use to tell this exact piece apart: cert, serial, catalogue numbers."""
    out = []
    c = item.condition
    if c and c.cert_number:
        out.append(f"{c.grading_service or 'Cert'} cert {c.cert_number}")
    if item.bar and item.bar.serial_number:
        out.append(f"Serial {item.bar.serial_number}")
    if item.banknote and item.banknote.serial_number:
        out.append(f"Serial {item.banknote.serial_number}")
    if item.goldback and item.goldback.serial_number:
        out.append(f"Serial {item.goldback.serial_number}")
    if item.banknote and item.banknote.pick_number:
        out.append(f"Pick {item.banknote.pick_number}")
    if item.coin and item.coin.pcgs_number:
        out.append(f"PCGS #{item.coin.pcgs_number}")
    return out


def metals_line(pure_total: dict[str, Decimal]) -> str:
    return ", ".join(f"{oz.normalize():f} ozt {METAL_NAMES.get(m, m)}" for m, oz in pure_total.items() if oz)


def basis(v: valuation.ItemValues) -> str:
    """Where the current value comes from, in words."""
    if v.rule_applied == "market" and v.market_valuation is not None:
        mv = v.market_valuation
        where = mv.source or ("sold listings" if mv.kind == "comps" else "your own figure")
        return f"Market value: {where}, {mv.as_of:%b %-d, %Y}"
    if v.rule_applied == "melt":
        return "Melt value at spot"
    if v.rule_applied == "cost":
        return "What was paid"
    return "No value yet"


# --- CSV -------------------------------------------------------------------------------------------

COLUMNS = [
    "ID", "Title", "Kind", "Status", "Quantity", "Description", "Country", "Denomination", "Year", "Mint mark", "Series",
    "Product line", "Grade", "Grading", "Grading service", "Cert number", "Serial number", "Refiner", "Weight", "Weight unit",
    "Gold ozt", "Silver ozt", "Platinum ozt", "Palladium ozt", "Currency", "Melt value", "Market value", "Market value from",
    "Market value date", "Current value", "Value basis", "Purchase price", "Purchase fees", "Cost", "Cost is", "Acquired",
    "Bought from", "Location", "Tags", "Sale date", "Sale price", "Sale fees", "Sold through", "Notes", "Numista ID",
    "PCGS number", "Added", "Updated",
]

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(v) -> str:
    """Text a spreadsheet won't run as a formula (a title starting with "=" stays text)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, Decimal | int | float):
        return str(v)
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v)
    return "'" + s if s.startswith(_FORMULA_START) else s


def csv_row(db: Session, item: Item, paths: dict[int, str | None], spot: dict, currency: str) -> list[str]:
    v = valuation.item_values(db, item, spot, currency=currency)
    mv = v.market_valuation
    coin, bar, note, cond = item.coin, item.bar, item.banknote, item.condition
    serial = (bar.serial_number if bar else None) or (note.serial_number if note else None)
    oz = {m: v.pure_toz_total.get(m) for m in ("Au", "Ag", "Pt", "Pd")}
    row = [
        item.id, item.title, KIND_LABELS.get(item.item_type, item.item_type), STATUS_LABELS.get(item.status, item.status),
        item.quantity, describe(item),
        (coin.country if coin else None) or (note.country if note else None),
        (coin.denomination if coin else None) or (note.denomination if note else None),
        coin.year if coin else None, coin.mint_mark if coin else None,
        (coin.series if coin else None) or (note.series if note else None), coin.product_line if coin else None,
        _grade_label(item), cond.grading if cond else None, cond.grading_service if cond else None, cond.cert_number if cond else None,
        serial, bar.refiner if bar else None, bar.weight_value if bar else None, bar.weight_unit if bar else None,
        oz["Au"], oz["Ag"], oz["Pt"], oz["Pd"], currency, v.melt, v.market, (mv.source or mv.kind) if mv else None,
        mv.as_of if mv else None, v.current, basis(v), item.purchase_price, item.purchase_fees, cost_basis(item),
        item.cost_basis_status, item.acquired_date, item.purchase_source,
        paths.get(item.location_id) if item.location_id else None, "; ".join(t.name for t in item.tags),
        item.sale_date, item.sale_price, item.sale_fees, item.sale_venue, item.notes,
        coin.numista_id if coin else None, coin.pcgs_number if coin else None, item.created_at, item.updated_at,
    ]
    return [_cell(c) for c in row]


def csv_stream(rows: Iterable[list[str]]) -> Iterator[str]:
    """The CSV, header first, with a byte-order mark so Excel reads it as UTF-8."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    buf.write("﻿")
    w.writerow(COLUMNS)
    for i, row in enumerate(rows):
        w.writerow(row)
        if i % 200 == 199:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    yield buf.getvalue()


# --- Insurance report ------------------------------------------------------------------------------


@dataclass
class ReportItem:
    id: int
    title: str
    kind: str
    status: str
    quantity: int
    description: str
    grade: str | None
    identifiers: list[str]
    metals: str
    location: str | None
    acquired_date: dt.date | None
    cost: Decimal | None
    current: Decimal | None
    current_each: Decimal | None
    basis: str
    photos: list[str]  # thumbnail URLs: the cover, then the next photo


@dataclass
class ReportGroup:
    label: str
    count: int = 0
    pieces: int = 0
    current: Decimal = ZERO


@dataclass
class Report:
    items: list[ReportItem] = field(default_factory=list)
    count: int = 0
    pieces: int = 0
    current: Decimal = ZERO
    melt: Decimal = ZERO
    cost: Decimal = ZERO
    cost_items: int = 0
    unvalued: int = 0
    by_location: list[ReportGroup] = field(default_factory=list)


def _photos(item: Item) -> list[str]:
    ordered = sorted(item.photos, key=lambda p: (p.id != item.cover_photo_id, p.sort_order, p.id))
    return [photo_urls(p.id, p.edits)["thumb"] for p in ordered[:2]]


def report(db: Session, items: list[Item], paths: dict[int, str | None], spot: dict, currency: str) -> Report:
    r = Report()
    groups: dict[str, ReportGroup] = {}
    for it in items:
        v = valuation.item_values(db, it, spot, currency=currency)
        loc = paths.get(it.location_id) if it.location_id else None
        r.items.append(ReportItem(
            id=it.id, title=it.title, kind=KIND_LABELS.get(it.item_type, it.item_type), status=STATUS_LABELS.get(it.status, it.status),
            quantity=it.quantity, description=describe(it), grade=_grade_label(it), identifiers=identifiers(it),
            metals=metals_line(v.pure_toz_total), location=loc, acquired_date=it.acquired_date, cost=v.cost, current=v.current,
            current_each=valuation.money(v.current / it.quantity) if v.current is not None and it.quantity > 1 else None,
            basis=basis(v), photos=_photos(it),
        ))
        r.count += 1
        r.pieces += it.quantity
        r.melt += v.melt or ZERO
        if v.cost is not None:
            r.cost += v.cost
            r.cost_items += 1
        g = groups.setdefault(loc or "", ReportGroup(loc or "No location"))
        g.count += 1
        g.pieces += it.quantity
        if v.current is None:
            r.unvalued += 1
        else:
            r.current += v.current
            g.current += v.current
    r.by_location = sorted(groups.values(), key=lambda g: (-g.current, g.label))
    return r
