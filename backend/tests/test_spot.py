import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from tests.m2_helpers import FakeProviders

NY = ZoneInfo("America/New_York")
WEDNESDAY = dt.datetime(2026, 10, 28, 11, 0, tzinfo=NY)
SATURDAY = dt.datetime(2026, 10, 31, 11, 0, tzinfo=NY)


@pytest.fixture
def db(app):
    from app.db import session_factory

    with session_factory()() as s:
        yield s


def _set_key(db, provider, key):
    from app.services import providers as psvc

    psvc.set_api_key(psvc.get_config(db, provider), key)
    db.commit()


def test_market_hours():
    from app.services.spot import market_open

    t = lambda *a: dt.datetime(*a, tzinfo=NY)  # noqa: E731
    assert market_open(t(2026, 10, 30, 16, 59))  # Friday before the close
    assert not market_open(t(2026, 10, 30, 17, 0))  # Friday close
    assert not market_open(t(2026, 10, 31, 12, 0))  # Saturday
    assert not market_open(t(2026, 11, 1, 17, 59))  # Sunday before the open (DST ends that morning)
    assert market_open(t(2026, 11, 1, 18, 0))  # Sunday open
    assert market_open(t(2026, 11, 2, 3, 0))  # Monday night session


def test_primary_provider_stores_every_metal(db):
    from app.models import ApiCallLog, SpotPrice
    from app.services import spot

    fake = FakeProviders()
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert out.ok and out.source == "gold_api"
    rows = {r.metal: r for r in db.scalars(select(SpotPrice))}
    assert set(rows) == {"Au", "Ag", "Pt", "Pd"}
    assert rows["Ag"].price_per_toz == Decimal("50.0000") and rows["Ag"].source == "gold_api"
    assert rows["Au"].source_timestamp is not None
    assert fake.calls == [f"api.gold-api.com/price/{s}/USD" for s in ("XAU", "XAG", "XPT", "XPD")]
    log = db.scalars(select(ApiCallLog)).all()
    assert [(l.status, l.cost) for l in log] == [("ok", 0)]


def test_fallback_to_metals_dev_and_quota_counted(db):
    from app.models import ProviderConfig, SpotPrice
    from app.services import providers as psvc
    from app.services import spot

    _set_key(db, "metals_dev", "md-key")
    fake = FakeProviders()
    fake.gold_api_status = 503
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert out.source == "metals_dev"
    assert "gold-api.com" in out.errors[0]
    assert db.scalar(select(SpotPrice.price_per_toz).where(SpotPrice.metal == "Ag")) == Decimal("50.2500")
    gold_cfg = db.scalar(select(ProviderConfig).where(ProviderConfig.provider_key == "gold_api"))
    assert gold_cfg.consecutive_failures == 1 and "503" in gold_cfg.last_error
    quota = psvc.quota_for(db, psvc.get_config(db, "metals_dev"))
    assert quota.used(WEDNESDAY) == 1
    assert "api.metals.dev/v1/latest" in fake.calls


def test_all_providers_fail_without_backup_key(db):
    from app.models import SpotPrice
    from app.services import spot

    fake = FakeProviders()
    fake.gold_api_status = 500
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert not out.ok
    assert db.scalar(select(SpotPrice)) is None
    assert not any("metals.dev" in c for c in fake.calls)  # no key, so never called


def test_backup_stops_at_cap(db):
    from app.services import providers as psvc
    from app.services import spot

    _set_key(db, "metals_dev", "md-key")
    cfg = psvc.get_config(db, "metals_dev")
    cfg.quota_cap = 2
    db.commit()
    psvc.quota_for(db, cfg).record(2, WEDNESDAY)
    db.commit()
    fake = FakeProviders()
    fake.gold_api_status = 500
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert not out.ok and any("cap" in e for e in out.errors)
    assert not any("metals.dev" in c for c in fake.calls)


def test_metals_dev_error_response(db):
    from app.services import spot

    _set_key(db, "metals_dev", "md-key")
    fake = FakeProviders()
    fake.gold_api_status = 500
    fake.metals_dev_body = {"status": "failure", "error_code": 1203, "error_message": "The quota for the current month is exceeded."}
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert not out.ok and "1203" in out.errors[-1]


def test_bad_price_is_rejected(db):
    from app.models import SpotPrice
    from app.services import spot

    fake = FakeProviders()
    fake.gold_api_body = {"currency": "USD", "price": "not-a-number", "symbol": "XAU"}
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert not out.ok and db.scalar(select(SpotPrice)) is None


def test_weekend_pause_and_force(db):
    from app.services import spot

    fake = FakeProviders()
    [out] = spot.poll(db, ["USD"], client=fake.client(), now=SATURDAY)
    assert out.skipped_reason == "markets closed" and fake.calls == []
    [forced] = spot.poll(db, ["USD"], client=fake.client(), now=SATURDAY, force=True)
    assert forced.ok


def test_stale_flags(db):
    from app.services import spot

    fake = FakeProviders()
    spot.poll(db, ["USD"], client=fake.client(), now=WEDNESDAY)
    assert not spot.latest(db, "USD", now=WEDNESDAY + dt.timedelta(minutes=29))["Ag"].stale
    assert spot.latest(db, "USD", now=WEDNESDAY + dt.timedelta(minutes=31))["Ag"].stale
    # Friday's last price is still current on Saturday: markets are closed.
    spot.poll(db, ["USD"], client=fake.client(), now=dt.datetime(2026, 10, 30, 16, 55, tzinfo=NY))
    assert not spot.latest(db, "USD", now=SATURDAY)["Ag"].stale
    assert spot.latest(db, "EUR", now=WEDNESDAY)["Ag"].stale  # never fetched
