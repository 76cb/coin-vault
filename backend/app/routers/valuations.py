"""Market values: typed in by the owner, or the median of eBay sold listings they pick (SoldComps)."""

from __future__ import annotations

import datetime as dt
import statistics
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crypto import EncryptionUnavailable
from app.db import get_db
from app.deps import Principal, read_items, write_items
from app.models import Item, Valuation, utcnow
from app.providers import soldcomps
from app.providers.base import ProviderError, http_client
from app.schemas import CompListing, CompsSearchIn, CompsSearchOut, CompsStats, ValuationIn, ValuationOut
from app.services import items as item_svc
from app.services import providers as psvc
from app.services.valuation import latest_valuation, money

router = APIRouter(tags=["valuations"])


def _item(db: Session, principal: Principal, item_id: int) -> Item:
    return item_svc.get_item(db, principal, item_id, False)


def _stats(prices: list[Decimal]) -> CompsStats:
    if not prices:
        return CompsStats(count=0, low=None, median=None, high=None)
    return CompsStats(count=len(prices), low=min(prices), median=money(statistics.median(prices)), high=max(prices))


def suggested_keyword(item: Item) -> str:
    """The title, plus grading service and grade for a slabbed coin when the title doesn't already say them."""
    kw = item.title.strip()
    c = item.condition
    if c is not None and c.grading == "slabbed":
        for part in (c.grading_service, c.grade_text):
            if part and part.lower() not in kw.lower():
                kw += f" {part}"
    return kw[:200]


def _with_use(item, principal) -> list[ValuationOut]:
    used = latest_valuation(item, principal.user.base_currency)
    return [ValuationOut.model_validate(v).model_copy(update={"in_use": used is not None and v.id == used.id}) for v in item.valuations]


@router.get("/items/{item_id}/valuations", response_model=list[ValuationOut])
def list_valuations(item_id: int, principal: Principal = Depends(read_items), db: Session = Depends(get_db)):
    return _with_use(_item(db, principal, item_id), principal)


class UseIn(BaseModel):
    use: bool  # true: use this value for the item; false: go back to the automatic choice


@router.put("/valuations/{valuation_id}/use", response_model=list[ValuationOut])
def use_valuation(valuation_id: int, body: UseIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Choose which market value counts for the item, or go back to the automatic choice. Returns the item's values."""
    v = db.get(Valuation, valuation_id)
    if v is None:
        raise HTTPException(404, "Valuation not found")
    item = _item(db, principal, v.item_id)
    for other in item.valuations:
        other.pinned = False
    v.pinned = body.use
    db.commit()
    db.refresh(item, ["valuations"])
    return _with_use(item, principal)


@router.post("/items/{item_id}/valuations", response_model=ValuationOut, status_code=201)
def add_valuation(item_id: int, body: ValuationIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    item = _item(db, principal, item_id)
    currency = principal.user.base_currency
    details = None
    value = body.value_each
    source = body.source
    if body.kind == "comps":
        sel = body.comps
        use = [l for l in sel.listings if (l.currency or currency) == currency]
        prices = [p for p in ((l.total_price or l.sold_price) if sel.basis == "total" else l.sold_price for l in use) if p]
        if not prices:
            raise HTTPException(422, f"None of the picked listings has a {currency} price")
        st = _stats(prices)
        value = st.median
        source = source or f"Median of {st.count} eBay sold listing{'s' if st.count != 1 else ''} (SoldComps)"
        details = {
            "keyword": sel.keyword,
            "basis": sel.basis,
            "count": st.count,
            "low": str(st.low),
            "median": str(st.median),
            "high": str(st.high),
            "listings": [l.model_dump(mode="json") for l in use],
        }
    v = Valuation(
        item_id=item.id,
        kind=body.kind,
        value_each=value,
        currency=currency,
        as_of=body.as_of or utcnow().date(),
        source=(source or "").strip() or None,
        notes=(body.notes or "").strip() or None,
        details=details,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@router.delete("/valuations/{valuation_id}", status_code=204)
def delete_valuation(valuation_id: int, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    v = db.get(Valuation, valuation_id)
    if v is None:
        raise HTTPException(404, "Valuation not found")
    _item(db, principal, v.item_id)  # 404 unless it's yours
    db.delete(v)
    db.commit()


@router.get("/items/{item_id}/comps/keyword")
def comps_keyword(item_id: int, principal: Principal = Depends(read_items), db: Session = Depends(get_db)) -> dict:
    return {"keyword": suggested_keyword(_item(db, principal, item_id))}


@router.post("/items/{item_id}/comps/search", response_model=CompsSearchOut)
def comps_search(item_id: int, body: CompsSearchIn, principal: Principal = Depends(write_items), db: Session = Depends(get_db)):
    """Searches eBay sold listings through SoldComps. Uses one SoldComps request; nothing is saved."""
    _item(db, principal, item_id)
    currency = principal.user.base_currency
    cfg = psvc.get_config(db, "soldcomps")
    if not cfg.enabled:
        raise HTTPException(409, "SoldComps is turned off in Settings → Data providers")
    try:
        key = psvc.api_key(cfg)
    except EncryptionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if not key:
        raise HTTPException(409, "Add your SoldComps API key in Settings → Data providers first")
    quota = psvc.quota_for(db, cfg)
    if quota is not None and not quota.can_spend(1):
        raise HTTPException(429, "Your SoldComps cap for this period is reached; raise it in Settings or wait for the reset")
    sold_after = None
    if body.sold_within_days:
        sold_after = (utcnow().date() - dt.timedelta(days=body.sold_within_days)).isoformat()
    with psvc.timed() as t, http_client() as client:
        try:
            result = soldcomps.search_sold(
                client, key, body.keyword, sold_after=sold_after, item_condition=body.condition, exact_match=body.exact_match
            )
        except ProviderError as exc:
            psvc.mark_failure(cfg, str(exc))
            psvc.log_call(db, "soldcomps", "/v1/scrape", "error", context=body.keyword, http_status=exc.http_status, detail=str(exc))
            db.commit()
            # 401: the saved key is wrong (fix it in Settings); 429: quota or rate limit; anything else is upstream
            code = {401: 409, 429: 429}.get(exc.http_status or 0, 502)
            raise HTTPException(code, str(exc)) from exc
    if quota is not None:
        quota.record(1)
        if result.usage is not None:
            quota.sync(result.usage)
    psvc.mark_success(cfg)
    psvc.log_call(db, "soldcomps", "/v1/scrape", "ok", context=body.keyword, cost=1, duration_ms=t["ms"],
                  detail=f"{len(result.listings)} sold listings")
    db.commit()
    listings = [CompListing(**l.__dict__) for l in result.listings]
    same = [l for l in listings if (l.currency or currency) == currency]
    return CompsSearchOut(
        keyword=result.keyword,
        total_results=result.total_results,
        has_more=result.has_next_page,
        currency=currency,
        listings=same,
        other_currency=len(listings) - len(same),
        stats=_stats([l.sold_price for l in same if l.sold_price]),
        requests_used=result.usage.used if result.usage else None,
        requests_limit=result.usage.limit if result.usage else None,
    )
