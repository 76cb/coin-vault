"""Numista catalogue: search it to fill in a new item, and save Numista's price estimate as a market value."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crypto import EncryptionUnavailable
from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import ProviderCache, Valuation, utcnow
from app.providers import numista
from app.providers.base import ProviderError, http_client
from app.schemas import ValuationOut
from app.services import items as item_svc
from app.services import providers as psvc
from app.services.coin_words import canonical_country

router = APIRouter(tags=["numista"])

TYPE_DAYS = 30  # coin details and issues change rarely
SEARCH_DAYS = 1
PRICE_DAYS = 1


class _Calls:
    """Numista requests for one API call of ours: key, monthly cap, logging and the cache."""

    def __init__(self, db: Session):
        self.db = db
        self.cfg = psvc.get_config(db, "numista")
        if not self.cfg.enabled:
            raise HTTPException(409, "Numista is turned off in Settings, Data providers")
        try:
            self.key = psvc.api_key(self.cfg)
        except EncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        if not self.key:
            raise HTTPException(409, "Add your Numista API key in Settings, Data providers first")
        self.quota = psvc.quota_for(db, self.cfg)
        self.client = http_client()

    def cached(self, cache_key: str, days: int, endpoint: str, fn: Callable[[numista.Numista], Any]) -> Any:
        row = self.db.get(ProviderCache, ("numista", cache_key))
        now = utcnow()
        if row is not None:
            fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=dt.UTC)
            if now - fetched < dt.timedelta(days=days):
                return row.data
        if self.quota is not None and not self.quota.can_spend(1):
            raise HTTPException(429, "This month's Numista requests are used up (your cap in Settings); they reset on the 1st")
        with psvc.timed() as t:
            try:
                data = fn(numista.Numista(self.client, self.key))
            except ProviderError as exc:
                if self.quota is not None and exc.cost:
                    self.quota.record(exc.cost)
                if exc.http_status == 401:
                    psvc.mark_failure(self.cfg, str(exc))
                psvc.log_call(self.db, "numista", endpoint, "error", context=cache_key, http_status=exc.http_status,
                              cost=exc.cost, detail=str(exc), duration_ms=t["ms"])
                self.db.commit()
                code = {401: 409, 404: 404, 429: 429, 400: 422}.get(exc.http_status or 0, 502)
                raise HTTPException(code, str(exc)) from exc
        if self.quota is not None:
            self.quota.record(1)
        psvc.mark_success(self.cfg)
        psvc.log_call(self.db, "numista", endpoint, "ok", context=cache_key, cost=1, duration_ms=t["ms"])
        if row is None:
            self.db.add(ProviderCache(provider_key="numista", cache_key=cache_key, data=data, fetched_at=now))
        else:
            row.data, row.fetched_at = data, now
        self.db.commit()
        return data

    def close(self):
        self.client.close()


def _calls(db: Session = Depends(get_db)):
    c = _Calls(db)
    try:
        yield c
    finally:
        c.close()


class NumistaHit(BaseModel):
    id: int
    title: str | None
    issuer: str | None
    min_year: int | None
    max_year: int | None
    obverse_thumbnail: str | None
    reverse_thumbnail: str | None


class NumistaSearchOut(BaseModel):
    count: int
    types: list[NumistaHit]


class NumistaIssueOut(BaseModel):
    id: int
    year: int | None
    gregorian_year: int | None
    mint_letter: str | None
    mintage: int | None
    comment: str | None


class NumistaTypeOut(BaseModel):
    id: int
    url: str | None
    title: str
    issuer: str | None
    min_year: int | None
    max_year: int | None
    denomination: str | None
    composition: str | None
    weight_g: Decimal | None
    size_mm: Decimal | None
    references: list[str]
    obverse_thumb: str | None
    reverse_thumb: str | None
    issues: list[NumistaIssueOut]
    # starting values for the item form, in the same shape as /items/describe
    item_type: str
    details: dict
    metal: dict | None  # {"metal", "gross_weight_g", "fineness"} from Numista's weight and composition


@router.get("/numista/search", response_model=NumistaSearchOut)
def search(
    q: str = Query(min_length=2, max_length=120),
    year: str | None = Query(default=None, pattern=r"^\d{1,4}(-\d{1,4})?$"),
    principal: Principal = Depends(read_items),
    calls: _Calls = Depends(_calls),
):
    """One Numista request (or none, when the same search was made today)."""
    key = f"search:{q.strip().lower()}|{year or ''}"[:200]
    data = calls.cached(key, SEARCH_DAYS, "types", lambda n: dict(zip(("count", "types"), n.search(q.strip(), year))))
    return NumistaSearchOut(count=data["count"], types=[NumistaHit(**t) for t in data["types"]])


@router.get("/numista/types/{type_id}", response_model=NumistaTypeOut)
def type_detail(type_id: int, principal: Principal = Depends(read_items), calls: _Calls = Depends(_calls)):
    """The coin and its issues: two Numista requests the first time, none for the next 30 days."""
    t = numista.to_type(calls.cached(f"type:{type_id}", TYPE_DAYS, "types/{id}", lambda n: n.type(type_id)))
    issues = numista.to_issues(calls.cached(f"issues:{type_id}", TYPE_DAYS, "types/{id}/issues", lambda n: n.issues(type_id)))
    parsed = numista.parse_composition(t.composition)
    metal = {"metal": parsed[0], "gross_weight_g": str(t.weight_g), "fineness": str(parsed[1])} if parsed and t.weight_g else None
    bullion = any(w in t.title.lower() for w in ("1 oz", "ounce", "onza", "bullion"))
    km = next((r.split("# ", 1)[1] for r in t.references if r.startswith("KM#")), None)
    details = {
        "country": canonical_country(t.issuer) if t.issuer else None,
        "denomination": t.denomination,
        "series": None if bullion else (t.series or None),
        "product_line": t.series if bullion else None,
        "numista_id": t.id,
        "diameter_mm": str(t.size_mm) if t.size_mm else None,
        "variety_notes": f"KM# {km}" if km else None,
    }
    return NumistaTypeOut(
        id=t.id, url=t.url, title=t.title, issuer=t.issuer, min_year=t.min_year, max_year=t.max_year,
        denomination=t.denomination, composition=t.composition, weight_g=t.weight_g, size_mm=t.size_mm,
        references=t.references, obverse_thumb=t.obverse_thumb, reverse_thumb=t.reverse_thumb,
        issues=[NumistaIssueOut(**vars(i)) for i in issues],
        item_type="bullion" if bullion else "coin",
        details={k: v for k, v in details.items() if v not in (None, "")},
        metal=metal,
    )


def _issue_for(item, issues: list[numista.NumistaIssue]) -> numista.NumistaIssue | None:
    """The item's issue: the one saved, else the only one matching its year and mint mark."""
    coin = item.coin
    if coin.numista_issue_id:
        return next((i for i in issues if i.id == coin.numista_issue_id), None)
    year, mark = coin.year, (coin.mint_mark or "").upper() or None
    if year is None:
        return issues[0] if len(issues) == 1 else None
    hits = [i for i in issues if year in (i.year, i.gregorian_year)]
    if mark is not None:
        hits = [i for i in hits if (i.mint_letter or "").upper() == mark] or hits
    return hits[0] if len(hits) == 1 else None


@router.post("/items/{item_id}/numista/estimate", response_model=ValuationOut, status_code=201)
def estimate(item_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db),
             calls: _Calls = Depends(_calls)):
    """Save Numista's price estimate for the item's issue and grade as a market value, in your display currency."""
    item = item_svc.get_item(db, principal, item_id, False)
    if item.coin is None or not item.coin.numista_id:
        raise HTTPException(422, "This needs the coin's Numista number (fill it in, or add the item from a Numista search)")
    cond = item.condition
    grade = numista.grade_for(cond.sheldon_grade if cond else None, cond.grade_text if cond else None)
    if grade is None:
        raise HTTPException(422, "Add the coin's grade first; Numista's estimates go by grade (G to Unc)")
    type_id = item.coin.numista_id
    issues = numista.to_issues(calls.cached(f"issues:{type_id}", TYPE_DAYS, "types/{id}/issues", lambda n: n.issues(type_id)))
    issue = _issue_for(item, issues)
    if issue is None:
        raise HTTPException(422, "Pick which issue (year and mint) this is: Numista lists several, or none match the year")
    currency = principal.user.base_currency
    data = calls.cached(f"prices:{type_id}:{issue.id}:{currency}", PRICE_DAYS, "prices",
                        lambda n: (lambda c, p: {"currency": c, "prices": {k: str(v) for k, v in p.items()}})(*n.prices(type_id, issue.id, currency)))
    prices = {k: Decimal(v) for k, v in data["prices"].items()}
    if data["currency"] != currency:
        raise HTTPException(502, f"Numista answered in {data['currency']}, not {currency}")
    if grade not in prices:
        have = ", ".join(numista.GRADE_NAMES[g] for g in numista.GRADES if g in prices) or "none"
        raise HTTPException(404, f"Numista has no estimate for this issue in {numista.GRADE_NAMES[grade]} (it has: {have})")
    if not item.coin.numista_issue_id:
        item.coin.numista_issue_id = issue.id
    label = numista.GRADE_NAMES[grade]
    others = ", ".join(f"{numista.GRADE_NAMES[g]} {prices[g]:,.2f}" for g in numista.GRADES if g in prices)
    v = Valuation(
        item_id=item.id, kind="manual", value_each=prices[grade], currency=currency, as_of=utcnow().date(),
        source=f"Numista estimate ({label})", notes=f"Numista's estimates for this issue: {others}.",
        details={"numista": {"type_id": type_id, "issue_id": issue.id, "grade": grade,
                             "prices": {k: str(p) for k, p in prices.items()}}},
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v
