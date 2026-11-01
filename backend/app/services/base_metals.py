"""What modern US coins with no precious metal are made of, by denomination and date: filled in on coin
items so their composition and weight show without anyone typing them. (Silver and gold issues have their
own reference rows and melt values; these never do.)

Figures: the US Mint's current specifications (https://www.usmint.gov/learn/coins-and-medals/circulating-coins/coin-specifications)
and, for earlier years, Wikipedia's article on each coin (cited per row).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.coin_words import US, canonical_country, us_denom

MINT = "https://www.usmint.gov/learn/coins-and-medals/circulating-coins/coin-specifications"
CENT = "https://en.wikipedia.org/wiki/Penny_(United_States_coin)"
NICKEL = "https://en.wikipedia.org/wiki/Nickel_(United_States_coin)"
CLAD = "Copper-nickel clad copper (91.67% copper, 8.33% nickel)"


@dataclass(frozen=True)
class BaseMetal:
    denomination: str  # US code: 1c, 5c, 10c, 25c, 50c, $1
    year_from: int
    year_to: int
    composition: str
    weight_g: Decimal | None
    source: str


ROWS: list[BaseMetal] = [
    BaseMetal("1c", 1856, 1864, "Copper-nickel (88% copper, 12% nickel)", Decimal("4.7"), CENT),
    BaseMetal("1c", 1864, 1942, "Bronze (95% copper, 5% tin and zinc)", Decimal("3.1"), CENT),
    BaseMetal("1c", 1943, 1943, "Zinc-coated steel", Decimal("2.7"), CENT),
    BaseMetal("1c", 1944, 1946, "Gilding metal (95% copper, 5% zinc)", Decimal("3.1"), CENT),
    BaseMetal("1c", 1947, 1961, "Bronze (95% copper, 5% tin and zinc)", Decimal("3.1"), CENT),
    BaseMetal("1c", 1962, 1981, "Gilding metal (95% copper, 5% zinc)", Decimal("3.1"), CENT),
    # 1982 cents were struck in both: weigh one to tell (3.1 g copper, 2.5 g zinc)
    BaseMetal("1c", 1982, 1982, "Gilding metal (95% copper) or copper-plated zinc: weigh it, 3.1 g or 2.5 g", None, CENT),
    BaseMetal("1c", 1983, 2100, "Copper-plated zinc (97.5% zinc, 2.5% copper)", Decimal("2.5"), MINT),
    BaseMetal("5c", 1866, 1941, "Copper-nickel (75% copper, 25% nickel)", Decimal("5.000"), NICKEL),
    BaseMetal("5c", 1942, 1942, "Copper-nickel (75% copper, 25% nickel)", Decimal("5.000"), NICKEL),  # not the P or S ones
    BaseMetal("5c", 1946, 2100, "Copper-nickel (75% copper, 25% nickel)", Decimal("5.000"), MINT),
    BaseMetal("10c", 1965, 2100, CLAD, Decimal("2.268"), MINT),
    BaseMetal("25c", 1965, 2100, CLAD, Decimal("5.670"), MINT),
    BaseMetal("50c", 1971, 2100, CLAD, Decimal("11.340"), MINT),
    BaseMetal("$1", 1971, 1978, CLAD, Decimal("22.68"), "https://en.wikipedia.org/wiki/Eisenhower_dollar"),
    BaseMetal("$1", 1979, 1981, "Copper-nickel clad copper (75% copper, 25% nickel over pure copper)", Decimal("8.1"),
              "https://en.wikipedia.org/wiki/Susan_B._Anthony_dollar"),
    BaseMetal("$1", 1999, 1999, "Copper-nickel clad copper (75% copper, 25% nickel over pure copper)", Decimal("8.1"),
              "https://en.wikipedia.org/wiki/Susan_B._Anthony_dollar"),
    BaseMetal("$1", 2000, 2100, "Manganese brass clad copper (88.5% copper, 6% zinc, 3.5% manganese, 2% nickel)", Decimal("8.1"), MINT),
]


def lookup(country: str | None, denomination: str | None, year: int | None, mint_mark: str | None = None,
           series: str | None = None) -> BaseMetal | None:
    """The base-metal make-up of a US coin of this denomination and date, or None (not US, a silver or gold
    issue, or a date this list doesn't cover)."""
    if year is None or (canonical_country(country) or country) != US:
        return None
    code = us_denom(denomination) or us_denom(series)
    if code is None:
        return None
    if code == "5c" and year == 1942 and (mint_mark or "").upper() in ("P", "S"):
        return None  # the wartime silver nickels carry a large P or S over Monticello
    return next((r for r in ROWS if r.denomination == code and r.year_from <= year <= r.year_to), None)
