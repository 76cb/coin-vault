"""Value history: what was held each day, at that day's spot price and the market values known then."""

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


def _today() -> dt.date:
    return dt.datetime.now(TZ).date()


def _day(n: int) -> str:
    return (_today() - dt.timedelta(days=n)).isoformat()


def _spot(metal: str, price: str, days_ago: int, currency: str = "USD"):
    from app.db import session_factory
    from app.models import SpotPrice, utcnow

    at = utcnow() - dt.timedelta(minutes=1) if days_ago == 0 else dt.datetime.combine(
        _today() - dt.timedelta(days=days_ago), dt.time(12), TZ).astimezone(dt.UTC)
    with session_factory()() as db:
        db.add(SpotPrice(metal=metal, currency=currency, price_per_toz=Decimal(price), source="gold_api", fetched_at=at))
        db.commit()


def _item(api, **body):
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _by_day(h):
    return {p["day"]: p for p in h["points"]}


def test_value_history(api):
    _spot("Ag", "20", 10)
    _spot("Ag", "25", 5)
    _spot("Ag", "30", 0)
    _item(api, item_type="bullion", title="Two rounds", quantity=2, acquired_date=_day(20), purchase_price="50",
          metal_content=[{"metal": "Ag", "pure_toz": "1"}])
    b = _item(api, item_type="coin", title="Copper rarity", acquired_date=_day(3), purchase_price="100")
    api.post(f"/api/v1/items/{b['id']}/valuations", json={"value_each": "120", "as_of": _day(2)})
    c = _item(api, item_type="coin", title="Ten ounces", acquired_date=_day(8), metal_content=[{"metal": "Ag", "pure_toz": "10"}])
    assert api.post(f"/api/v1/items/{c['id']}/sell", json={"sale_date": _day(4), "sale_price": "300"}).status_code == 200

    h = api.get("/api/v1/portfolio/history?days=30").json()
    assert h["clipped"] and h["start"] == _day(10) and h["first_spot"] == _day(10) and h["step_days"] == 1
    days = _by_day(h)
    v = lambda n: Decimal(days[_day(n)]["value"])  # noqa: E731
    assert v(10) == 40 and v(9) == 40  # two rounds at 20
    assert v(8) == 240  # plus the ten ounces
    assert v(5) == 300  # at 25
    assert v(4) == 50  # the ten ounces were sold that day
    assert v(3) == 50 and days[_day(3)]["unvalued"] == 1  # the copper coin has no value until it's priced
    assert v(2) == 170 and Decimal(days[_day(2)]["paid"]) == 150
    assert v(0) == 180
    assert h["added"] == {"count": 2, "amount": "100.00"} and h["sold"] == {"count": 1, "amount": "300.00"}
    assert h["undated"] == 0 and h["no_cost"] == 0

    # today matches the dashboard
    assert Decimal(api.get("/api/v1/portfolio/summary").json()["totals"]["current"]) == v(0)

    silver = _by_day(api.get("/api/v1/portfolio/history?days=30&metal=Ag").json())
    assert Decimal(silver[_day(2)]["value"]) == 50 and Decimal(silver[_day(8)]["value"]) == 240
    bullion = _by_day(api.get("/api/v1/portfolio/history?days=30&type=bullion").json())
    assert Decimal(bullion[_day(8)]["value"]) == 40
    assert api.get("/api/v1/portfolio/history?type=nonsense").status_code == 422


def test_market_value_counts_from_its_date(api):
    """A value dated last week isn't used for the weeks before it; a pinned value only from its own date."""
    it = _item(api, item_type="coin", title="Graded", acquired_date=_day(30), purchase_price="10",
               condition={"grading": "slabbed", "grading_service": "PCGS", "grade_text": "MS65"})
    api.post(f"/api/v1/items/{it['id']}/valuations", json={"value_each": "40", "as_of": _day(20)})
    pinned = api.post(f"/api/v1/items/{it['id']}/valuations", json={"value_each": "25", "as_of": _day(5)}).json()
    api.post(f"/api/v1/items/{it['id']}/valuations", json={"value_each": "60", "as_of": _day(1)})
    api.put(f"/api/v1/valuations/{pinned['id']}/use", json={"use": True})
    days = _by_day(api.get("/api/v1/portfolio/history?days=30").json())
    assert days[_day(25)]["unvalued"] == 1
    assert Decimal(days[_day(10)]["value"]) == 40
    assert Decimal(days[_day(5)]["value"]) == 25 and Decimal(days[_day(0)]["value"]) == 25  # chosen from its date on


def test_long_ranges_go_weekly_and_undated_items_count_from_when_added(api):
    _spot("Au", "2000", 600)
    _spot("Au", "4000", 0)
    _item(api, item_type="bullion", title="Old eagle", acquired_date=_day(700), metal_content=[{"metal": "Au", "pure_toz": "1"}])
    _item(api, item_type="bullion", title="No date", metal_content=[{"metal": "Au", "pure_toz": "0.1"}])
    h = api.get("/api/v1/portfolio/history?days=0").json()
    assert h["step_days"] == 7 and h["clipped"] and h["undated"] == 1 and h["no_cost"] == 2
    assert h["points"][-1]["day"] == _today().isoformat() and Decimal(h["points"][-1]["value"]) == 4400
    assert Decimal(h["points"][0]["value"]) == 2000 and h["points"][0]["items"] == 1


def test_empty_and_no_spot(api):
    h = api.get("/api/v1/portfolio/history").json()
    assert h["points"][-1]["items"] == 0 and len(h["points"]) == 1
    _item(api, item_type="bullion", title="Unpriced", acquired_date=_day(40), metal_content=[{"metal": "Ag", "pure_toz": "1"}])
    h = api.get("/api/v1/portfolio/history").json()
    assert h["first_spot"] is None and h["clipped"] and len(h["points"]) == 1 and h["points"][0]["unvalued"] == 1
