"""Checklists, the sales (realized gains) report, QR codes for labels and CSV import."""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, read_items, require_scope, write_items
from app.models import Item, Location, utcnow
from app.routers.describe import described_out
from app.schemas import ItemCreate
from app.services import checklists as cl
from app.services import items as item_svc
from app.services.describe import describe
from app.services.valuation import ZERO, money

router = APIRouter(tags=["more"])
read_export = require_scope("export")

# --- Checklists ----------------------------------------------------------------------------------


class ChecklistSummary(BaseModel):
    key: str
    name: str
    note: str
    total: int
    have: int


class HaveOut(BaseModel):
    id: int
    title: str
    in_set: bool


class EntryOut(BaseModel):
    label: str
    group: str
    have: list[HaveOut]


class ChecklistOut(ChecklistSummary):
    entries: list[EntryOut]


def _today_year() -> int:
    return utcnow().year


@router.get("/checklists", response_model=list[ChecklistSummary])
def list_checklists(principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    held = cl.holdings(db, principal.owner_id)
    out = []
    for c in cl.all_checklists(_today_year()):
        rows = cl.progress(c, held)
        out.append(ChecklistSummary(key=c.key, name=c.name, note=c.note, total=len(rows), have=sum(1 for _, h in rows if h)))
    return out


@router.get("/checklists/{key}", response_model=ChecklistOut)
def get_checklist(key: str, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    c = next((c for c in cl.all_checklists(_today_year()) if c.key == key), None)
    if c is None:
        raise HTTPException(404, "No such checklist")
    rows = cl.progress(c, cl.holdings(db, principal.owner_id))
    return ChecklistOut(
        key=c.key, name=c.name, note=c.note, total=len(rows), have=sum(1 for _, h in rows if h),
        entries=[EntryOut(label=e.label, group=e.group, have=[HaveOut(id=h.item_id, title=h.title, in_set=h.in_set) for h in hs])
                 for e, hs in rows],
    )


# --- Sales: what was sold, and the gain on it ---------------------------------------------------------


class SaleRow(BaseModel):
    id: int
    title: str
    quantity: int
    acquired_date: dt.date | None
    sale_date: dt.date
    sale_venue: str | None
    sale_price: Decimal
    sale_fees: Decimal
    proceeds: Decimal  # sale price less selling fees
    cost: Decimal | None  # price paid plus fees; None when not recorded
    cost_estimated: bool
    gain: Decimal | None
    days_held: int | None
    long_term: bool | None  # held more than a year; None when the acquired date isn't recorded


class SalesYear(BaseModel):
    year: int
    count: int
    proceeds: Decimal
    cost: Decimal
    gain: Decimal  # over the sales with a cost
    gain_short: Decimal
    gain_long: Decimal
    gain_undated: Decimal  # gain on sales with no acquired date, so the holding period isn't known
    no_cost: int


class SalesOut(BaseModel):
    currency: str
    years: list[SalesYear]
    sales: list[SaleRow]


@router.get("/reports/sales", response_model=SalesOut)
def sales_report(year: int | None = None, principal: Principal = Depends(read_export), db: Session = Depends(get_db)):
    """Every sold item with its proceeds, cost and gain, and totals by year. A record for your own tax preparation,
    not tax advice: "long term" here only means held more than a year."""
    stmt = select(Item).where(Item.owner_id == principal.owner_id, Item.deleted_at.is_(None), Item.status == "sold",
                              Item.sale_date.is_not(None), Item.sale_price.is_not(None))
    rows: list[SaleRow] = []
    years: dict[int, SalesYear] = {}
    for it in db.scalars(stmt.order_by(Item.sale_date.desc(), Item.id.desc())):
        fees = it.sale_fees or ZERO
        proceeds = money(it.sale_price - fees)
        cost = money(item_svc.cost_basis(it))
        gain = None if cost is None else proceeds - cost
        days = (it.sale_date - it.acquired_date).days if it.acquired_date else None
        long_term = None if days is None else days > 365
        y = years.setdefault(it.sale_date.year, SalesYear(year=it.sale_date.year, count=0, proceeds=ZERO, cost=ZERO, gain=ZERO,
                                                          gain_short=ZERO, gain_long=ZERO, gain_undated=ZERO, no_cost=0))
        y.count += 1
        y.proceeds += proceeds
        if gain is None:
            y.no_cost += 1
        else:
            y.cost += cost
            y.gain += gain
            if long_term is None:
                y.gain_undated += gain
            elif long_term:
                y.gain_long += gain
            else:
                y.gain_short += gain
        if year is None or it.sale_date.year == year:
            rows.append(SaleRow(
                id=it.id, title=it.title, quantity=it.quantity, acquired_date=it.acquired_date, sale_date=it.sale_date,
                sale_venue=it.sale_venue, sale_price=money(it.sale_price), sale_fees=money(fees), proceeds=proceeds, cost=cost,
                cost_estimated=it.cost_basis_status == "estimated", gain=gain, days_held=days, long_term=long_term,
            ))
    return SalesOut(currency=principal.user.base_currency, years=sorted(years.values(), key=lambda y: -y.year), sales=rows)


# --- QR codes, for printed storage labels -----------------------------------------------------------


@router.get("/reference/qr.svg")
def qr_svg(text: str = Query(min_length=1, max_length=500), _: Principal = Depends(read_items)):
    """A QR code of the given text (a link to a storage location's contents, for a label)."""
    import zxingcpp

    try:
        svg = zxingcpp.write_barcode_to_svg(zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode))
    except Exception as exc:
        raise HTTPException(422, "That text can't be made into a QR code") from exc
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=86400"})


# --- CSV import -------------------------------------------------------------------------------------

MAX_IMPORT_ROWS = 2000
KINDS = {"coin": "coin", "bullion": "bullion", "bullion coin or round": "bullion", "mint set": "set", "set": "set", "bar": "bar",
         "banknote": "banknote", "goldback": "goldback", "junk silver lot": "lot", "lot": "lot", "other": "other"}
METAL_COLUMNS = {"gold ozt": "Au", "silver ozt": "Ag", "platinum ozt": "Pt", "palladium ozt": "Pd"}
STATUSES = {"owned": "owned", "for sale": "for_sale", "for_sale": "for_sale", "sold": "sold"}
ALIASES = {"name": "title", "type": "kind", "qty": "quantity", "mint": "mint mark", "mintmark": "mint mark",
           "price": "purchase price", "price paid": "purchase price", "paid": "purchase price", "cost": "purchase price",
           "fees": "purchase fees", "date": "acquired", "date acquired": "acquired", "purchase date": "acquired",
           "source": "bought from", "dealer": "bought from", "from": "bought from", "cert": "cert number", "service": "grading service",
           "storage": "location", "note": "notes", "tag": "tags", "serial": "serial number"}


class ImportRow(BaseModel):
    line: int
    title: str
    ok: bool
    error: str | None = None
    kind: str | None = None
    summary: str | None = None  # what will be saved: metal, cost and so on
    item_id: int | None = None


class ImportOut(BaseModel):
    dry_run: bool
    columns_used: list[str]
    columns_ignored: list[str]
    rows: list[ImportRow]
    ok: int
    failed: int
    created: int


def _num(v: str) -> Decimal | None:
    t = re.sub(r"[,$€£\s]", "", v or "")
    if not t:
        return None
    try:
        return Decimal(t)
    except InvalidOperation as exc:
        raise ValueError(f"{v!r} is not a number") from exc


def _date(v: str) -> dt.date | None:
    v = (v or "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(v[:10] if fmt == "%Y-%m-%d" else v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{v!r} is not a date I can read (use 2026-11-15 or 11/15/2026)")


def _location_id(db: Session, owner_id: int, path: str, cache: dict[str, int], create: bool) -> int | None:
    """The location with this path ("Safe › Box A"), made if it isn't there yet (only when saving)."""
    parts = [p.strip() for p in re.split(r"\s*[›>]\s*|\s+/\s+", path) if p.strip()]
    if not parts:
        return None
    key = " › ".join(parts).lower()
    if key in cache:
        return cache[key]
    parent = None
    for name in parts:
        row = db.scalar(select(Location).where(Location.owner_id == owner_id, Location.parent_id.is_(None) if parent is None else Location.parent_id == parent,
                                               Location.name == name))
        if row is None:
            if not create:
                return None
            row = Location(owner_id=owner_id, parent_id=parent, name=name)
            db.add(row)
            db.flush()
        parent = row.id
    cache[key] = parent
    return parent


def _row_item(db: Session, principal: Principal, r: dict[str, str], cache: dict[str, int], create: bool) -> tuple[ItemCreate, str]:
    """One CSV row as an item. The title is read the way the quick add box reads it; columns then say more."""
    title = r.get("title", "").strip()
    if not title:
        raise ValueError("no title")
    d = described_out(db, principal, describe(title))
    kind = KINDS.get(r.get("kind", "").strip().lower()) if r.get("kind", "").strip() else d.item_type
    if kind is None:
        raise ValueError(f"unknown kind {r['kind']!r}")
    qty = int(_num(r.get("quantity", "")) or d.quantity or 1)
    details = dict(d.details) if kind == d.item_type else {}
    cols = {"coin": {"country": "country", "denomination": "denomination", "year": "year", "mint mark": "mint_mark", "series": "series",
                     "product line": "product_line", "pcgs number": "pcgs_number", "numista id": "numista_id"},
            "bar": {"refiner": "refiner", "weight": "weight_value", "weight unit": "weight_unit", "serial number": "serial_number"},
            "banknote": {"country": "country", "denomination": "denomination", "series": "series", "serial number": "serial_number"},
            "set": {"country": "country", "year": "year", "mint mark": "mint_mark"}}
    for col, field in cols.get("coin" if kind == "bullion" else kind, {}).items():
        if r.get(col, "").strip():
            details[field] = r[col].strip()
    condition = d.condition if kind == d.item_type else None
    if r.get("cert number", "").strip() or r.get("grading service", "").strip() or r.get("grade", "").strip():
        service = r.get("grading service", "").strip() or (condition or {}).get("grading_service")
        grade = r.get("grade", "").strip() or (condition or {}).get("grade_text")
        if service and grade and grade.upper().startswith(service.upper()):
            grade = grade[len(service):].strip()
        condition = {**(condition or {}), "grading": "slabbed" if service else "raw", "grading_service": service or None,
                     "grade_text": grade or None, "cert_number": (r.get("cert number", "").strip() or None) if service else None,
                     "designations": (condition or {}).get("designations", [])}
        if not (condition.get("sheldon_grade")):
            m = re.search(r"(\d{1,2})", grade or "")
            condition["sheldon_grade"] = int(m.group(1)) if m and 1 <= int(m.group(1)) <= 70 else None
    metal: list[dict] = []
    typed = {m: _num(r.get(col, "")) for col, m in METAL_COLUMNS.items()}
    best = d.compositions[0] if d.compositions and sum(1 for c in d.compositions if c.score == d.compositions[0].score) == 1 else None
    how = "no metal"
    if kind in ("set", "goldback"):
        how = "metal from its contents"
    elif any(v for v in typed.values()):  # the export gives ounces for the whole row: per piece here
        metal = [{"metal": m, "pure_toz": (v / qty).quantize(Decimal("0.000001"))} for m, v in typed.items() if v]
        how = "metal from the file"
    elif kind == "lot":
        if best is not None and best.per_face_unit:
            details["composition_id"] = best.id
            how = f"metal: {best.label}"
    elif best is not None and not best.per_face_unit and kind == d.item_type:
        metal = [{"metal": best.metal, "composition_id": best.id}]
        how = f"metal: {best.label}"
    elif d.stamped is not None and d.stamped.fineness is not None and kind == d.item_type:
        metal = [{"metal": d.stamped.metal, "gross_weight_g": d.stamped.gross_weight_g, "fineness": d.stamped.fineness}]
        how = "metal from the weight in the title" + (" (fineness assumed .999)" if d.stamped.fineness_assumed else "")
    status = STATUSES.get(r.get("status", "").strip().lower() or "owned")
    if status is None:
        raise ValueError(f"unknown status {r['status']!r}")
    price = _num(r.get("purchase price", ""))
    notes = "\n".join(x for x in (r.get("notes", "").strip(), *(d.notes if kind == d.item_type else [])) if x) or None
    body = ItemCreate(
        item_type=kind, title=title[:200], quantity=qty, status=status, details=details, condition=condition, metal_content=metal,
        purchase_price=price, purchase_fees=_num(r.get("purchase fees", "")), acquired_date=_date(r.get("acquired", "")),
        purchase_source=r.get("bought from", "").strip() or None, notes=notes,
        tags=[t.strip() for t in re.split(r"[;,]", r.get("tags", "")) if t.strip()],
        location_id=_location_id(db, principal.owner_id, r.get("location", ""), cache, create),
        sale_date=_date(r.get("sale date", "")) if status == "sold" else None,
        sale_price=_num(r.get("sale price", "")) if status == "sold" else None,
        sale_fees=_num(r.get("sale fees", "")) if status == "sold" else None,
        sale_venue=(r.get("sold through", "").strip() or None) if status == "sold" else None,
    )
    if status == "sold" and (body.sale_date is None or body.sale_price is None):
        raise ValueError("a sold row needs a Sale date and a Sale price")
    summary = ", ".join(x for x in (how, f"paid {price}" if price is not None else "no cost", f"×{qty}" if qty > 1 else "") if x)
    return body, summary


@router.post("/import/items", response_model=ImportOut)
async def import_items(
    file: UploadFile = File(...), dry_run: bool = True, principal: Principal = Depends(write_items), db: Session = Depends(get_db),
):
    """Add items from a CSV file. Only a Title column is needed: each title is read the way the quick add box reads
    it (kind, year, grade, metal). Other columns, named as in this app's own CSV export, fill in more. With dry_run
    (the default) nothing is saved and the answer shows what each row would become."""
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(413, "That file is too big (5 MB at most)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise HTTPException(422, "The file is empty") from None
    names = []
    for h in header:
        n = re.sub(r"\s+", " ", h.strip().lstrip("'").lower())
        names.append(ALIASES.get(n, n))
    if "title" not in names:
        raise HTTPException(422, "The file needs a Title column (the first row must be the column names)")
    known = {"title", "kind", "quantity", "status", "country", "denomination", "year", "mint mark", "series", "product line", "grade",
             "grading service", "cert number", "serial number", "refiner", "weight", "weight unit", *METAL_COLUMNS, "purchase price",
             "purchase fees", "acquired", "bought from", "location", "tags", "sale date", "sale price", "sale fees", "sold through",
             "notes", "numista id", "pcgs number"}
    rows: list[ImportRow] = []
    cache: dict[str, int] = {}
    created = 0
    for line, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(rows) >= MAX_IMPORT_ROWS:
            raise HTTPException(422, f"Too many rows: {MAX_IMPORT_ROWS} at most in one file")
        r: dict[str, str] = {}
        for n, c in zip(names, cells):
            # the export puts a ' before text a spreadsheet would run as a formula: taken off again here
            r.setdefault(n, c[1:] if c[:2] in ("'=", "'+", "'-", "'@") else c)
        title = r.get("title", "").strip()
        try:
            with db.begin_nested():
                body, summary = _row_item(db, principal, r, cache, create=not dry_run)
                item_id = None
                if not dry_run:
                    item_id = item_svc.create_item(db, principal, body).id
                    created += 1
            rows.append(ImportRow(line=line, title=title, ok=True, kind=body.item_type, summary=summary, item_id=item_id))
        except (ValueError, ValidationError, HTTPException) as exc:
            msg = exc.detail if isinstance(exc, HTTPException) else str(exc)
            if isinstance(exc, ValidationError):
                e = exc.errors()[0]
                msg = f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}"
            rows.append(ImportRow(line=line, title=title or "(no title)", ok=False, error=str(msg)[:300]))
    if dry_run:
        db.rollback()
    else:
        db.commit()
    ok = sum(1 for r in rows if r.ok)
    return ImportOut(dry_run=dry_run, columns_used=[h.strip() for h, n in zip(header, names) if n in known],
                     columns_ignored=[h.strip() for h, n in zip(header, names) if n not in known and h.strip()],
                     rows=rows, ok=ok, failed=len(rows) - ok, created=created)
