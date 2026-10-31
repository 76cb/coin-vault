"""Weekly value updates: the PCGS price guide values and Numista estimates you've fetched, fetched again.

Only items that already have a value from that source are updated (fetching one is how an item joins), so the
weekly run never spends lookups on items you haven't asked about. A new value is saved as a new dated market
value, which is what the value history follows; an unchanged one just records that it was checked. Values you
chose with "Use this" stay chosen. Each source stops for the week when its cap (Settings) is reached.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.logging_setup import log
from app.models import Item, User, Valuation, utcnow
from app.services import providers as psvc

RECHECK_DAYS = 6  # a value fetched (or checked) this recently is left alone


@dataclass
class SourceResult:
    checked: int = 0  # looked up
    changed: int = 0  # a new value saved
    failed: int = 0
    skipped: int = 0  # fetched or checked within the last few days
    stopped: str | None = None  # why the source stopped early (cap reached, no key…)


@dataclass
class UpdateResult:
    started_at: str
    finished_at: str | None = None
    pcgs: SourceResult = field(default_factory=SourceResult)
    numista: SourceResult = field(default_factory=SourceResult)
    errors: list[str] = field(default_factory=list)  # the first few, for Settings


def _source_of(v: Valuation) -> str | None:
    d = v.details or {}
    return "pcgs" if "pcgs" in d else "numista" if "numista" in d else None


def _last_seen(v: Valuation) -> dt.date:
    checked = (v.details or {}).get("checked")
    try:
        return max(v.as_of, dt.date.fromisoformat(checked)) if checked else v.as_of
    except ValueError:
        return v.as_of


def _due(db: Session, source: str, today: dt.date) -> list[tuple[Item, Valuation]]:
    """Held items with a value from this source, and that newest value, when it's older than RECHECK_DAYS."""
    items = db.scalars(
        select(Item).where(Item.deleted_at.is_(None), Item.status != "sold")
        .options(selectinload(Item.valuations), selectinload(Item.coin), selectinload(Item.condition))
        .order_by(Item.id)
    )
    out = []
    for it in items:
        latest = next((v for v in it.valuations if _source_of(v) == source), None)  # newest first
        if latest is not None and (today - _last_seen(latest)).days >= RECHECK_DAYS:
            out.append((it, latest))
    return out


def _save(db: Session, new: Valuation, latest: Valuation, today: dt.date, r: SourceResult) -> None:
    r.checked += 1
    if new.value_each == latest.value_each and new.currency == latest.currency:
        latest.details = {**(latest.details or {}), "checked": today.isoformat()}
    else:
        new.details = {**(new.details or {}), "auto": True}
        new.notes = ("Weekly update. " + (new.notes or "")).strip()
        db.add(new)
        r.changed += 1
    db.commit()


def _fail(r: SourceResult, out: UpdateResult, item: Item, exc: HTTPException) -> bool:
    """Record a failure; True when the source should stop for this run."""
    if exc.status_code in (409, 429, 503):  # no key, turned off, cap reached, keys locked
        r.stopped = str(exc.detail)
        return True
    r.failed += 1
    if len(out.errors) < 8:
        out.errors.append(f"{item.title}: {exc.detail}")
    return False


def run(db: Session, now: dt.datetime | None = None) -> UpdateResult:
    from app.routers import numista as numista_router
    from app.routers import pcgs as pcgs_router

    now = now or utcnow()
    today = now.date()
    out = UpdateResult(started_at=now.isoformat())
    owners = {u.id: u for u in db.scalars(select(User))}

    due = _due(db, "pcgs", today)
    for item, latest in due:
        if owners.get(item.owner_id) is None or owners[item.owner_id].base_currency != "USD":
            out.pcgs.skipped += 1  # PCGS prices are in US dollars
            continue
        try:
            coin = pcgs_router.price_guide_lookup(db, item)
            if coin.price_guide is None:
                raise HTTPException(404, f"PCGS has no price guide value now for {coin.grade or 'its grade'}")
            _save(db, pcgs_router.price_guide_valuation(item, coin), latest, today, out.pcgs)
        except HTTPException as exc:
            db.rollback()
            if _fail(out.pcgs, out, item, exc):
                break

    due = _due(db, "numista", today)
    if due:
        try:
            calls = numista_router._Calls(db)
        except HTTPException as exc:
            out.numista.stopped = str(exc.detail)
            calls = None
        if calls is not None:
            try:
                for item, latest in due:
                    currency = owners[item.owner_id].base_currency if item.owner_id in owners else "USD"
                    try:
                        _save(db, numista_router.estimate_valuation(calls, item, currency), latest, today, out.numista)
                    except HTTPException as exc:
                        db.rollback()
                        if _fail(out.numista, out, item, exc):
                            break
            finally:
                calls.close()

    out.finished_at = utcnow().isoformat()
    log.info("value_updates", pcgs=asdict(out.pcgs), numista=asdict(out.numista))
    return out


def run_and_record(db: Session) -> UpdateResult:
    """Run, and keep the outcome for Settings (also when it crashes)."""
    psvc.set_system(db, "updates_running", utcnow().isoformat())  # when it started; a stale one (a restart mid-run) is ignored
    db.commit()
    try:
        result = run(db)
        psvc.set_system(db, "updates_last", {**asdict(result), "ok": True})
        return result
    except Exception as exc:
        log.exception("value_updates_crashed")
        db.rollback()
        psvc.set_system(db, "updates_last", {"started_at": utcnow().isoformat(), "finished_at": utcnow().isoformat(),
                                             "ok": False, "errors": [str(exc)[:300]]})
        raise
    finally:
        psvc.set_system(db, "updates_running", None)
        db.commit()


def is_running(db: Session) -> bool:
    started = psvc.get_system(db, "updates_running")
    if not started:
        return False
    try:
        t = dt.datetime.fromisoformat(started)
    except (TypeError, ValueError):
        return False
    return utcnow() - (t if t.tzinfo else t.replace(tzinfo=dt.UTC)) < dt.timedelta(hours=2)
