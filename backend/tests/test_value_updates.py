"""Weekly value updates: PCGS price guide values and Numista estimates fetched again, with history."""

import datetime as dt
from decimal import Decimal

import pytest

from tests.m2_helpers import FakeProviders


@pytest.fixture
def fake(monkeypatch):
    f = FakeProviders()
    import app.routers.numista as n
    import app.routers.pcgs as p
    import app.services.provider_admin as pa

    for mod in (n, p, pa):
        monkeypatch.setattr(mod, "http_client", f.client)
    return f


def _age(valuation_id: int, days: int, value: str | None = None):
    """Make a saved value look `days` old (and optionally different), as if fetched back then."""
    from app.db import session_factory
    from app.models import Valuation, utcnow

    with session_factory()() as db:
        v = db.get(Valuation, valuation_id)
        v.as_of = utcnow().date() - dt.timedelta(days=days)
        if value is not None:
            v.value_each = Decimal(value)
        db.commit()


def _pcgs_item(api, title, days, value=None):
    it = api.post("/api/v1/items", json={"item_type": "coin", "title": title,
                                         "condition": {"grading": "slabbed", "grading_service": "PCGS", "cert_number": "32573628"}}).json()
    v = api.post(f"/api/v1/items/{it['id']}/pcgs/price-guide").json()
    _age(v["id"], days, value)
    return it


def _values(api, item_id):
    return api.get(f"/api/v1/items/{item_id}/valuations").json()


def test_weekly_update(api, fake):
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "pcgs-token"})
    api.put("/api/v1/settings/providers/numista", json={"api_key": "numista-key"})
    moved = _pcgs_item(api, "Price moved", 10, value="40")  # PCGS now says 45
    same = _pcgs_item(api, "Price the same", 8)
    fresh = _pcgs_item(api, "Fetched yesterday", 1)
    untracked = api.post("/api/v1/items", json={"item_type": "coin", "title": "Never priced",
                                                "condition": {"grading": "slabbed", "grading_service": "PCGS", "cert_number": "32573628"}}).json()
    canada = api.post("/api/v1/items", json={"item_type": "coin", "title": "1858 Canada 5 cents",
                                             "details": {"year": 1858, "numista_id": 420},
                                             "condition": {"grading": "raw", "sheldon_grade": 30}}).json()
    nv = api.post(f"/api/v1/items/{canada['id']}/numista/estimate").json()
    _age(nv["id"], 9, value="25")
    calls_before = len(fake.pcgs_calls)

    r = api.post("/api/v1/value-updates")
    assert r.status_code == 202 and r.json()["running"]
    st = api.get("/api/v1/value-updates").json()
    assert not st["running"] and st["last"]["ok"]
    assert st["last"]["pcgs"] == {"checked": 2, "changed": 1, "failed": 0, "skipped": 0, "stopped": None}
    assert st["last"]["numista"]["checked"] == 1 and st["last"]["numista"]["changed"] == 1
    assert st["tracked_pcgs"] == 3 and st["tracked_numista"] == 1
    assert len(fake.pcgs_calls) - calls_before == 2  # only the two that were due

    today = dt.date.today().isoformat()
    m = _values(api, moved["id"])
    assert [Decimal(v["value_each"]) for v in m] == [45, 40]  # the old value stays, as history
    assert m[0]["as_of"] == today and m[0]["notes"].startswith("Weekly update.")
    assert Decimal(api.get(f"/api/v1/items/{moved['id']}").json()["values"]["market_each"]) == 45
    s = _values(api, same["id"])
    assert len(s) == 1  # unchanged: no new row
    assert len(_values(api, fresh["id"])) == 1 and _values(api, untracked["id"]) == []
    c = _values(api, canada["id"])
    assert [Decimal(v["value_each"]) for v in c] == [30, 25]

    # right away again: nothing is due
    api.post("/api/v1/value-updates")
    last = api.get("/api/v1/value-updates").json()["last"]
    assert last["pcgs"]["checked"] == 0 and last["numista"]["checked"] == 0


def test_cap_and_missing_key_stop_a_source(api, fake):
    api.put("/api/v1/settings/providers/pcgs", json={"api_key": "pcgs-token", "quota_cap": 2})
    a = _pcgs_item(api, "A", 10)  # uses 1 of 2
    b = _pcgs_item(api, "B", 10)  # uses 2 of 2
    api.post("/api/v1/value-updates")
    last = api.get("/api/v1/value-updates").json()["last"]
    assert last["pcgs"]["checked"] == 0 and "used up" in last["pcgs"]["stopped"]
    assert len(_values(api, a["id"])) == 1 and len(_values(api, b["id"])) == 1
    assert last["numista"]["stopped"] is None  # nothing from Numista to update


def test_settings_and_admin_only(api, app, make_user):
    from fastapi.testclient import TestClient

    from tests.conftest import Api

    st = api.get("/api/v1/value-updates").json()
    assert st["enabled"] and st["day"] == "sun" and st["time"] == "05:40" and st["last"] is None
    out = api.put("/api/v1/value-updates/settings", json={"enabled": True, "day": "wed", "time": "6:05"}).json()
    assert out["day"] == "wed" and out["time"] == "06:05"
    assert api.put("/api/v1/value-updates/settings", json={"enabled": True, "day": "xyz", "time": "06:05"}).status_code == 422
    with TestClient(app) as c:
        make_user("viewer2", admin=False)
        other = Api(c)
        other.login("viewer2")
        assert other.get("/api/v1/value-updates").status_code == 403
        assert other.post("/api/v1/value-updates").status_code == 403
