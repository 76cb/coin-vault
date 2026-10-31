import datetime as dt

import pytest

from app.providers.base import UsageInfo

UTC = dt.UTC


@pytest.fixture
def db(app):
    from app.db import session_factory

    with session_factory()() as s:
        yield s


def qm(db, cap=90, kind="calendar_month", key="metals_dev"):
    from app.services.quota import QuotaManager

    return QuotaManager(db, key, cap, kind)


def test_counts_and_stops_at_cap(db):
    now = dt.datetime(2026, 10, 15, tzinfo=UTC)
    q = qm(db, cap=3)
    assert q.remaining(now) == 3 and q.can_spend(1, now)
    q.record(2, now)
    assert q.used(now) == 2 and q.can_spend(1, now) and not q.can_spend(2, now)
    q.record(1, now)
    assert q.remaining(now) == 0 and not q.can_spend(1, now)


def test_count_persists_across_restarts(db):
    now = dt.datetime(2026, 10, 15, tzinfo=UTC)
    qm(db).record(5, now)
    db.commit()
    from app.db import session_factory

    with session_factory()() as fresh:
        assert qm(fresh).used(now) == 5


def test_calendar_month_resets_on_the_first(db):
    q = qm(db)
    q.record(40, dt.datetime(2026, 10, 31, 23, 59, tzinfo=UTC))
    assert q.used(dt.datetime(2026, 11, 1, 0, 0, tzinfo=UTC)) == 0
    p = q.period(dt.datetime(2026, 12, 20, tzinfo=UTC))
    assert p.period_start.replace(tzinfo=UTC) == dt.datetime(2026, 12, 1, tzinfo=UTC)
    assert p.period_end.replace(tzinfo=UTC) == dt.datetime(2027, 1, 1, tzinfo=UTC)


def test_provider_counts_win_and_billing_anchor_is_adopted(db):
    now = dt.datetime(2026, 10, 20, tzinfo=UTC)
    q = qm(db, cap=90, kind="billing_cycle", key="soldcomps")
    q.record(3, now)  # counted under an assumed calendar month
    info = UsageInfo(
        used=12, limit=100, remaining=88,
        period_start=dt.datetime(2026, 10, 14, tzinfo=UTC), period_end=dt.datetime(2026, 11, 14, tzinfo=UTC),
    )
    row = q.sync(info, now)
    assert row.used == 12 and row.provider_limit == 100
    assert q.used(now) == 12 and q.remaining(now) == 78  # our cap (90) is lower than the plan (100)
    # After the anchor date the count starts again, on the provider's cycle.
    later = q.period(dt.datetime(2026, 11, 20, tzinfo=UTC))
    assert later.period_start.replace(tzinfo=UTC) == dt.datetime(2026, 11, 14, tzinfo=UTC)
    assert later.used == 0


def test_provider_limit_below_cap(db):
    now = dt.datetime(2026, 10, 20, tzinfo=UTC)
    q = qm(db, cap=500, key="metals_dev")
    q.sync(UsageInfo(used=95, limit=100, remaining=5, period_start=None, period_end=None), now)
    assert q.remaining(now) == 5
