"""Mint and proof sets: one item, the coins inside it listed and searchable, its silver added up from them."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from app.services import mint_sets
from app.services.describe import describe

Q2008 = "2008 United States 50 State Quarters Silver Proof Set"


def _create(api, body: dict) -> dict:
    r = api.post("/api/v1/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _from_title(api, title: str, **extra) -> dict:
    d = api.post("/api/v1/items/describe", json={"text": title}).json()
    return _create(api, {"item_type": d["item_type"], "title": d["title"], "quantity": d["quantity"], "details": d["details"], **extra})


def test_set_contents_by_year():
    q = mint_sets.contents(2008, "silver_proof", quarters_only=True)
    assert [c.label for c in q.coins] == [f"2008-S {s} quarter" for s in ("Oklahoma", "New Mexico", "Arizona", "Alaska", "Hawaii")]
    assert q.name == "50 State Quarters Silver Proof Set" and q.pure_toz() == {"Ag": Decimal("0.904240")}
    # coins per set, as the Mint sold them
    counts = {1992: 5, 1998: 5, 1999: 9, 2000: 10, 2004: 11, 2005: 11, 2006: 10, 2007: 14, 2008: 14, 2009: 18, 2015: 14,
              2016: 13, 2017: 10, 2020: 10, 2021: 7, 2024: 10}
    assert {y: len(mint_sets.contents(y, "silver_proof").coins) for y in counts} == counts
    full = mint_sets.contents(2008, "silver_proof")
    assert full.pure_toz() == {"Ag": Decimal("1.338275")}  # dime + 5 quarters + half, 90%
    assert sum(1 for c in full.coins if c.metal == "Ag") == 7 and "2008-S Martin Van Buren Presidential dollar" in [c.label for c in full.coins]
    assert mint_sets.contents(2022, "silver_proof").pure_toz() == {"Ag": Decimal("1.507549")}  # .999 from 2019
    # clad sets hold no silver, except the 40% half of 1968-1970 and everything before 1965
    assert mint_sets.contents(2008, "proof").pure_toz() == {}
    assert mint_sets.contents(1969, "proof").pure_toz() == {"Ag": Decimal("0.147893")}
    old = mint_sets.contents(1962, "proof")
    assert old.mint_mark is None and [c.label for c in old.coins][-1] == "1962 Franklin half dollar" and old.pure_toz() == {"Ag": Decimal("0.614883")}
    assert "1776-1976-S Bicentennial Washington quarter" in [c.label for c in mint_sets.contents(1976, "proof").coins]
    for year, kind in ((1942, "proof"), (1966, "proof"), (1991, "silver_proof"), (2026, "proof"), (1998, "uncirculated")):
        assert mint_sets.contents(year, kind) is None


@pytest.mark.parametrize("title, kind, coins, quarters", [
    (Q2008, "silver_proof", 5, True),
    ("2008-S State Quarters Silver Proof Set- with box & certificate of authenticity", "silver_proof", 5, True),
    ("2008 14-Coin Silver Proof Set with Statehood Quarters and Presidential Dollars", "silver_proof", 14, False),
    ("2021 Silver Proof Set 7 coins", "silver_proof", 7, False),
    ("2003 US Mint Proof Set", "proof", 10, False),
    ("1987 US Mint Uncirculated Coin Set", "uncirculated", 0, False),
    ("2010 Canada Proof Set", "proof", 0, False),
])
def test_titles_read_as_sets(title, kind, coins, quarters):
    d = describe(title)
    assert d.item_type == "set" and d.quantity == 1 and d.details["set_kind"] == kind
    assert len(d.details.get("coins", [])) == coins
    assert ("Quarters" in d.details["name"]) == quarters
    assert d.composition_key is None


def test_a_graded_coin_from_a_set_stays_a_coin():
    assert describe("1964 Kennedy half dollar from proof set PCGS PR67").item_type == "coin"


def test_set_silver_comes_from_its_coins(api):
    item = _from_title(api, Q2008, purchase_price="42.00")
    assert item["item_type"] == "set" and item["details"]["name"] == "50 State Quarters Silver Proof Set"
    assert item["details"]["year"] == 2008 and item["details"]["mint_mark"] == "S" and item["details"]["set_kind"] == "silver_proof"
    coins = item["details"]["coins"]
    assert [c["label"] for c in coins][0] == "2008-S Oklahoma quarter" and len(coins) == 5
    assert all(c["metal"] == "Ag" and Decimal(c["pure_toz"]) == Decimal("0.180848") for c in coins)
    assert [(m["metal"], Decimal(m["pure_toz"]), m["source"]) for m in item["metal_content"]] == [("Ag", Decimal("0.904240"), "computed")]
    assert Decimal(item["metal_content"][0]["gross_weight_g"]) == Decimal("31.25") and Decimal(item["metal_content"][0]["fineness"]) == Decimal("0.9")
    assert Decimal(item["pure_toz_per_unit"]["Ag"]) == Decimal("0.904240")

    # two of the same set: the totals double, the coin list stays per set
    v = item["version"]
    two = api.patch(f"/api/v1/items/{item['id']}", json={"quantity": 2}, headers={"If-Match": str(v)}).json()
    assert Decimal(two["values"]["pure_toz_total"]["Ag"]) == Decimal("1.808480") and len(two["details"]["coins"]) == 5


def test_search_finds_a_set_by_any_coin_in_it(api):
    quarters = _from_title(api, Q2008)
    full = _from_title(api, "2012 S Silver Proof Set OGP")
    _create(api, {"item_type": "coin", "title": "1881-S Morgan Dollar", "details": {"country": "United States", "denomination": "$1", "year": 1881}})

    def found(q: str, **params) -> dict[int, dict]:
        return {i["id"]: i for i in api.get("/api/v1/items", params={"q": q, **params}).json()["items"]}

    hit = found("oklahoma")
    assert set(hit) == {quarters["id"]} and hit[quarters["id"]]["matched_coins"] == ["2008-S Oklahoma quarter"]
    assert hit[quarters["id"]]["coin_count"] == 5 and hit[quarters["id"]]["year"] == 2008 and hit[quarters["id"]]["country"] == "United States"
    assert set(found("Denali")) == {full["id"]}
    assert set(found("presidential")) == {full["id"]} and len(found("presidential")[full["id"]]["matched_coins"]) == 4
    assert set(found("quarter")) == {quarters["id"], full["id"]}
    assert set(found("2008")) == {quarters["id"]} and set(found("silver proof set")) == {quarters["id"], full["id"]}
    assert set(found("", type="set")) == {quarters["id"], full["id"]} and found("morgan", type="set") == {}
    assert set(found("", metal="Ag")) == {quarters["id"], full["id"]}
    # the CSV export uses the same search, and its description lists the coins
    csv = api.get("/api/v1/export/items.csv?q=hawaii").text
    assert "Mint set" in csv and "2008-S Hawaii quarter" in csv and "5 coins" in csv and "2012" not in csv


def test_editing_the_coins(api):
    item = _from_title(api, Q2008)
    url, coins = f"/api/v1/items/{item['id']}", item["details"]["coins"]

    def patch(body: dict, it: dict) -> dict:
        r = api.patch(url, json=body, headers={"If-Match": str(it["version"])})
        assert r.status_code == 200, r.text
        return r.json()

    # details sent without the coins keep them
    item = patch({"details": {"name": "State Quarters Silver Proof Set"}}, item)
    assert len(item["details"]["coins"]) == 5 and item["details"]["year"] == 2008
    # one quarter taken out, a gold coin by reference and a hand-typed medal put in
    age = next(c for c in api.get("/api/v1/compositions").json() if c["key"] == "age-tenth")
    new = coins[:4] + [
        {"label": "1/10 oz Gold Eagle", "composition_id": age["id"]},
        {"label": "Silver medal", "quantity": 2, "metal": "Ag", "weight_g": "10", "fineness": "0.925", "pure_toz": "9"},  # weight x fineness wins
        {"label": "Bronze token", "weight_g": "5", "composition": "Bronze"},
    ]
    item = patch({"details": {"coins": new}}, item)
    by = {m["metal"]: m for m in item["metal_content"]}
    assert Decimal(by["Au"]["pure_toz"]) == Decimal("0.1")
    medal = Decimal("10") / Decimal("31.1034768") * Decimal("0.925")
    assert Decimal(by["Ag"]["pure_toz"]) == (4 * Decimal("0.180848") + 2 * medal.quantize(Decimal("0.000001")))
    assert by["Ag"]["fineness"] is None  # mixed finenesses: no single figure
    assert item["details"]["coins"][-1]["metal"] is None and item["details"]["coins"][-1]["pure_toz"] is None
    audit = api.get(f"{url}/audit").json()
    assert any(a["field"] == "metal_content" for a in audit)
    # a bad reference is refused
    r = api.patch(url, json={"details": {"coins": [{"label": "x", "composition_id": 999999}]}}, headers={"If-Match": str(item["version"])})
    assert r.status_code == 422
    r = api.patch(url, json={"details": {"coins": [{"label": ""}]}}, headers={"If-Match": str(item["version"])})
    assert r.status_code == 422
    # turned into a plain coin, the coin list goes
    item = patch({"item_type": "coin", "details": {"country": "United States"}}, item)
    assert "coins" not in item["details"]
    back = patch({"item_type": "set"}, item)
    assert back["details"]["coins"] == []


def test_a_set_without_listed_coins_keeps_its_own_metal(api):
    item = _create(api, {"item_type": "set", "title": "1987 Uncirculated Mint Set", "details": {"year": 1987, "set_kind": "uncirculated"},
                         "metal_content": [{"metal": "Ag", "gross_weight_g": "10", "fineness": "0.5"}]})
    assert item["details"]["coins"] == [] and Decimal(item["metal_content"][0]["pure_toz"]) == Decimal("0.160754")
    assert api.post("/api/v1/items", json={"item_type": "set", "title": "x", "details": {"set_kind": "nonsense"}}).status_code == 422


def test_geiger_bars_are_recognised(api):
    bar = api.post("/api/v1/items/describe", json={"text": "Geiger Edelmetalle 100 g Silver Bar .999 square"}).json()
    assert bar["item_type"] == "bar" and bar["details"]["refiner"] == "Geiger Edelmetalle"
    assert bar["compositions"][0]["key"] == "bar-geiger-edelmetalle-ag-100-g-999" and Decimal(bar["compositions"][0]["pure_toz"]) == Decimal("3.211860")
    gold = api.post("/api/v1/items/describe", json={"text": "1 oz Gold Bar Geiger original 9999 in capsule"}).json()
    assert gold["compositions"][0]["key"] == "bar-geiger-edelmetalle-au-1-oz-9999"
    card = api.post("/api/v1/items/describe", json={"text": "Geiger Multicard 25 x 1 g silver bar"}).json()
    assert card["compositions"][0]["key"] == "bar-geiger-edelmetalle-silver-multicard-25-x-1-g"
    item = _create(api, {"item_type": "bar", "title": "Geiger 100 g silver", "details": bar["details"],
                         "metal_content": [{"metal": "Ag", "composition_id": bar["compositions"][0]["id"]}]})
    assert Decimal(item["metal_content"][0]["pure_toz"]) == Decimal("3.211860") and item["metal_content"][0]["source"] == "reference"


def test_saved_silver_proof_sets_are_broken_out_by_the_migration(tmp_path):
    """A set saved the old way (a coin with the denomination "set" on its reference figure) becomes a set with coins;
    one whose silver was typed by hand is left alone."""
    from alembic import command

    from app.migrate import alembic_config

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")

    def upgrade(rev: str) -> None:
        cfg = alembic_config()
        with engine.connect() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, rev)

    upgrade("0014")
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, username, password_hash, is_admin, is_active, base_currency, created_at) "
                       "VALUES (1, 'u', 'x', 1, 1, 'USD', '2026-01-01')"))
        comp = c.execute(text("SELECT id FROM compositions WHERE key = 'us-set-quarters-states'")).scalar_one()
        for item_id, title in ((1, "2008-S State Quarters Silver Proof Set"), (2, "2007-S State Quarters Silver Proof Set")):
            c.execute(text("INSERT INTO items (id, owner_id, item_type, title, quantity, status, cost_basis_status, valuation_rule, version, "
                           "created_at, updated_at) VALUES (:id, 1, 'coin', :t, 1, 'owned', 'unknown', 'max', 1, '2026-01-01', '2026-01-01')"),
                      {"id": item_id, "t": title})
            c.execute(text("INSERT INTO coin_details (item_id, country, denomination, year, series) VALUES "
                           "(:id, 'United States', 'set', :y, 'Quarters Silver Proof Set')"), {"id": item_id, "y": 2009 - item_id})
        c.execute(text("INSERT INTO item_metal_content (item_id, metal, pure_toz, source, composition_id) VALUES (1, 'Ag', 0.90424, 'reference', :c)"), {"c": comp})
        c.execute(text("INSERT INTO item_metal_content (item_id, metal, pure_toz, source) VALUES (2, 'Ag', 0.9, 'override')"))
    upgrade("head")
    with engine.connect() as c:
        assert c.execute(text("SELECT id, item_type FROM items ORDER BY id")).all() == [(1, "set"), (2, "coin")]
        assert c.execute(text("SELECT label FROM set_coins WHERE item_id = 1 ORDER BY seq")).scalars().all()[::4] == [
            "2008-S Oklahoma quarter", "2008-S Hawaii quarter"]
        assert c.execute(text("SELECT name, year, mint_mark, set_kind FROM set_details")).all() == [
            ("50 State Quarters Silver Proof Set", 2008, "S", "silver_proof")]
        metal, pure, source = c.execute(text("SELECT metal, pure_toz, source FROM item_metal_content WHERE item_id = 1")).one()
        assert (metal, Decimal(str(pure)), source) == ("Ag", Decimal("0.90424"), "computed")
        assert c.execute(text("SELECT count(*) FROM coin_details")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM compositions WHERE key LIKE 'bar-geiger-%'")).scalar_one() == 26
    engine.dispose()
