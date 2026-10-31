"""Foreign coins and world bullion: the title parser and the reference matcher together."""

import pytest

from app.services.coin_words import canonical_country, denom_key, find_country, find_foreign_denomination, us_denom


def keys(api, text):
    r = api.post("/api/v1/items/describe", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json(), [c["key"] for c in r.json()["compositions"]]


@pytest.mark.parametrize(("text", "key"), [
    ("Half Crown", "0.5 crown"), ("half-crown", "0.5 crown"), ("1/2 crown", "0.5 crown"),
    ("5 Pesos", "5 peso"), ("five peso", "5 peso"), ("2½ pesos", "2.5 peso"), ("2 1/2 Azadi", "2.5 azadi"),
    ("1 Yuan (7 Mace 2 Candareens)", "1 yuan"), ("Threepence", "3 penny"), ("3 pence", "3 penny"),
    ("10 Cents", "10 cent"), ("10c", "10 cent"), ("$5", "5 dollar"), ("5 Bolívares", "5 bolivar"),
    ("Double Florin", "2 florin"), ("Rupee", "1 rupee"), ("8 Reales", "8 real"),
])
def test_denom_key(text, key):
    assert denom_key(text) == key


def test_words():
    assert us_denom("Half Dime") == "5c" and us_denom("Half Dollar") == "50c" and us_denom("Trade Dollar") == "trade$1"
    assert canonical_country("Great Britain") == "United Kingdom" and canonical_country("usa") == "United States"
    assert canonical_country("Narnia") == "Narnia"
    assert find_country("1964 Canada 50 cents") == "Canada" and find_country("Swiss 20 francs") == "Switzerland"
    assert find_country("the us coin") is None and find_country("US Morgan") == "United States"
    assert find_foreign_denomination("1922 Mexico 2 pesos gold") == "2 pesos"
    assert find_foreign_denomination("Mexico 2½ pesos") == "2 1/2 pesos"
    assert find_foreign_denomination("no mint mark") is None
    assert find_foreign_denomination("1964 pesos") == "pesos"  # a year is not an amount


def test_foreign_coins(api):
    d, k = keys(api, "1964 Canada 50 cents silver")
    assert d["details"]["country"] == "Canada" and k[:1] == ["cat-canada-50-cents-80-silver-1920-1967"]
    d, k = keys(api, "1937 Great Britain half crown George VI")
    assert d["details"]["denomination"] == "half crown"
    assert k and all(key.startswith("cat-united-kingdom-") for key in k)
    d, k = keys(api, "1922 Mexico 2 pesos gold")
    assert k[:1] == ["cat-mexico-2-pesos-gold-1919-1948"]
    d, k = keys(api, "1880 Japan 1 yen silver NGC XF45")
    assert k[:1] == ["cat-japan-meiji-silver-1-yen"] and d["condition"]["grade_text"] == "XF45"
    d, k = keys(api, "1921 Chinese Fat Man dollar")
    assert "cat-china-yuan-shikai-fat-man-dollar" in k
    # a dime with no country is still a US dime, not a Canadian 10 cents
    _, k = keys(api, "1950 dime")
    assert k and all(not key.startswith("cat-canada") for key in k)


def test_world_bullion_sizes(api):
    _, k = keys(api, "2024 1/4 oz Gold Britannia")
    assert k[:1] == ["cat-united-kingdom-gold-britannia-1-4-oz-9999-2013"]
    _, k = keys(api, "1995 1/4 oz Gold Britannia")
    assert k[:1] == ["cat-united-kingdom-gold-britannia-1-4-oz-22-ct-1987-2012"]
    _, k = keys(api, "2023 30g Gold Panda")
    assert k[:1] == ["cat-china-chinese-gold-panda-30-g-2016"]
    _, k = keys(api, "1/10 oz Mexico Gold Libertad 2020")
    assert k[:1] == ["cat-mexico-gold-libertad-1-10-oz-999-1991-present"]
    d, k = keys(api, "2018 2 oz Silver Queens Beasts Lion")
    assert d["details"]["product_line"] == "Silver Queen's Beasts" and k[:1] == ["cat-united-kingdom-queen-s-beasts-silver-2-oz"]


def test_ounce_bullion_needs_a_size(api):
    # the 5 oz America the Beautiful coin is a "quarter" too, but only a title giving a size should suggest it
    _, k = keys(api, "2015-S Bombay Hook NP Silver Proof Quarter")
    assert "cat-united-states-america-the-beautiful-5-oz-silver-2010-2021" not in k
    r = api.get("/api/v1/compositions/match", params={"country": "US", "denomination": "quarter", "year": 2015,
                                                       "series": "America the Beautiful 5 oz silver"})
    assert "cat-united-states-america-the-beautiful-5-oz-silver-2010-2021" in [c["key"] for c in r.json()]


def test_european_coins(api):
    _, k = keys(api, "1935-B Swiss 20 francs gold Vreneli")
    assert k[:1] == ["cat-switzerland-20-francs-gold-vreneli"]
    _, k = keys(api, "1912 A German Empire 20 Mark gold Wilhelm II")
    assert k[:1] == ["cat-germany-german-empire-20-mark-gold"]
    _, k = keys(api, "1966 France 10 francs Hercule silver")
    assert k[:1] == ["cat-france-10-francs-silver-hercule-1965-1973"]
    _, k = keys(api, "1780 Maria Theresa Thaler restrike Austria")
    assert k[:1] == ["cat-austria-maria-theresa-thaler-1780-restrike"]


def test_second_batch(api):
    _, k = keys(api, "1945 Newfoundland 10 cents silver")
    assert k[:1] == ["cat-newfoundland-10-cents-silver-800-george-vi-1945-1947"]
    _, k = keys(api, "2008-W 1/2 oz Gold Buffalo")
    assert k[:1] == ["cat-united-states-american-gold-buffalo-1-2-oz-9999-2008"]
    _, k = keys(api, "1880 Denmark 20 kroner gold")
    assert k[:1] == ["cat-denmark-20-kroner-gold-900-1873-1917"]
    _, k = keys(api, "1951 Belgium 20 francs Mercury silver")
    assert k[:1] == ["cat-belgium-20-francs-silver-835-mercury-1949-1955"]
    _, k = keys(api, "1938 Hungary 5 pengő")
    assert k[:1] == ["cat-hungary-5-peng-silver-640-regular-issue-1938-1939"]
