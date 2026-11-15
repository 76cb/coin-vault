"""What is inside the US Mint's annual sets, year by year, so a set can be recorded as one item with every
coin in it listed (and found by search), and its silver added up from the coins that have any.

Covered: proof sets 1936-1941 and 1950-2025, silver proof sets 1992-2025, and the quarters-only proof sets
(clad and silver) 1999-2025. Not covered, because their contents vary by packaging or weren't checked:
1942 proof sets (five or six coins), uncirculated mint sets, Prestige, Premier and Limited Edition sets and
the 1976 three-coin 40% silver set. Those are typed in coin by coin.

Sources (checked 2026-11-15):
- Quarter designs: the US Mint's 50 State Quarters page (usmint.gov/learn/coins-and-medals/circulating-coins/
  quarter/50-state-quarters) for 1999-2008; the Mint's programme pages for the later series.
- Coins per set: proofsetguide.com's page for each year (5 coins 1992-1998, 9 in 1999, 14 in 2007-2008,
  18 in 2009, 7 in 2021).
- Silver coin weights and fineness: the reference rows in compositions_seed (US Mint specifications);
  base-metal coins: services/base_metals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.services import base_metals

TROY = Decimal("31.1034768")
Q = Decimal("0.000001")
US = "United States"

KIND_LABELS = {"proof": "Proof set", "silver_proof": "Silver proof set", "uncirculated": "Uncirculated mint set",
               "special": "Special mint set", "other": "Other set"}

STATE_QUARTERS: dict[int, list[str]] = {
    1999: ["Delaware", "Pennsylvania", "New Jersey", "Georgia", "Connecticut"],
    2000: ["Massachusetts", "Maryland", "South Carolina", "New Hampshire", "Virginia"],
    2001: ["New York", "North Carolina", "Rhode Island", "Vermont", "Kentucky"],
    2002: ["Tennessee", "Ohio", "Louisiana", "Indiana", "Mississippi"],
    2003: ["Illinois", "Alabama", "Maine", "Missouri", "Arkansas"],
    2004: ["Michigan", "Florida", "Texas", "Iowa", "Wisconsin"],
    2005: ["California", "Minnesota", "Oregon", "Kansas", "West Virginia"],
    2006: ["Nevada", "Nebraska", "Colorado", "North Dakota", "South Dakota"],
    2007: ["Montana", "Washington", "Idaho", "Wyoming", "Utah"],
    2008: ["Oklahoma", "New Mexico", "Arizona", "Alaska", "Hawaii"],
}
TERRITORY_QUARTERS = ["District of Columbia", "Puerto Rico", "Guam", "American Samoa", "U.S. Virgin Islands",
                      "Northern Mariana Islands"]
ATB_QUARTERS: dict[int, list[str]] = {
    2010: ["Hot Springs", "Yellowstone", "Yosemite", "Grand Canyon", "Mount Hood"],
    2011: ["Gettysburg", "Glacier", "Olympic", "Vicksburg", "Chickasaw"],
    2012: ["El Yunque", "Chaco Culture", "Acadia", "Hawai'i Volcanoes", "Denali"],
    2013: ["White Mountain", "Perry's Victory", "Great Basin", "Fort McHenry", "Mount Rushmore"],
    2014: ["Great Smoky Mountains", "Shenandoah", "Arches", "Great Sand Dunes", "Everglades"],
    2015: ["Homestead", "Kisatchie", "Blue Ridge Parkway", "Bombay Hook", "Saratoga"],
    2016: ["Shawnee", "Cumberland Gap", "Harpers Ferry", "Theodore Roosevelt", "Fort Moultrie"],
    2017: ["Effigy Mounds", "Frederick Douglass", "Ozark Riverways", "Ellis Island", "George Rogers Clark"],
    2018: ["Pictured Rocks", "Apostle Islands", "Voyageurs", "Cumberland Island", "Block Island"],
    2019: ["Lowell", "American Memorial Park", "War in the Pacific", "San Antonio Missions", "Frank Church River of No Return"],
    2020: ["National Park of American Samoa", "Weir Farm", "Salt River Bay", "Marsh-Billings-Rockefeller", "Tallgrass Prairie"],
}
QUARTERS_2021 = [("Tuskegee Airmen", "America the Beautiful"), ("Washington Crossing the Delaware", "Washington")]
WOMEN_QUARTERS: dict[int, list[str]] = {
    2022: ["Maya Angelou", "Dr. Sally Ride", "Wilma Mankiller", "Nina Otero-Warren", "Anna May Wong"],
    2023: ["Bessie Coleman", "Edith Kanaka'ole", "Eleanor Roosevelt", "Jovita Idar", "Maria Tallchief"],
    2024: ["Patsy Takemoto Mink", "Dr. Mary Edwards Walker", "Pauli Murray", "Zitkala-Sa", "Celia Cruz"],
    2025: ["Ida B. Wells", "Juliette Gordon Low", "Dr. Vera Rubin", "Stacey Park Milbern", "Althea Gibson"],
}
PRESIDENTS: dict[int, list[str]] = {
    2007: ["George Washington", "John Adams", "Thomas Jefferson", "James Madison"],
    2008: ["James Monroe", "John Quincy Adams", "Andrew Jackson", "Martin Van Buren"],
    2009: ["William Henry Harrison", "John Tyler", "James K. Polk", "Zachary Taylor"],
    2010: ["Millard Fillmore", "Franklin Pierce", "James Buchanan", "Abraham Lincoln"],
    2011: ["Andrew Johnson", "Ulysses S. Grant", "Rutherford B. Hayes", "James A. Garfield"],
    2012: ["Chester A. Arthur", "Grover Cleveland (first term)", "Benjamin Harrison", "Grover Cleveland (second term)"],
    2013: ["William McKinley", "Theodore Roosevelt", "William Howard Taft", "Woodrow Wilson"],
    2014: ["Warren G. Harding", "Calvin Coolidge", "Herbert Hoover", "Franklin D. Roosevelt"],
    2015: ["Harry S. Truman", "Dwight D. Eisenhower", "John F. Kennedy", "Lyndon B. Johnson"],
    2016: ["Richard M. Nixon", "Gerald R. Ford", "Ronald Reagan"],
}
NICKELS = {2004: ["Peace Medal", "Keelboat"], 2005: ["American Bison", "Ocean in View"]}
CENTS_2009 = ["Birthplace", "Formative Years", "Professional Life", "Presidency"]
CENT_2009 = "Bronze (95% copper, 3% zinc, 2% tin), as in 1909"  # the proof-set cents only; circulating ones are zinc

# (weight g, fineness) of the silver issues
SILVER_90 = {"10c": ("2.50", "0.900"), "25c": ("6.25", "0.900"), "50c": ("12.50", "0.900")}
SILVER_999 = {"10c": ("2.537", "0.999"), "25c": ("6.343", "0.999"), "50c": ("12.685", "0.999")}
HALF_40 = ("11.50", "0.400")
DENOM_WORDS = {"1c": "cent", "5c": "nickel", "10c": "dime", "25c": "quarter", "50c": "half dollar", "$1": "dollar"}


@dataclass(frozen=True)
class SetCoinSpec:
    label: str
    denomination: str
    year: int
    mint_mark: str | None
    series: str | None = None
    quantity: int = 1
    composition: str | None = None
    weight_g: Decimal | None = None
    metal: str | None = None
    fineness: Decimal | None = None
    pure_toz: Decimal | None = None

    def as_dict(self) -> dict:
        """As the item form and API take it: numbers as strings, blanks left out."""
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class SetSpec:
    name: str
    kind: str
    year: int
    mint_mark: str | None
    coins: list[SetCoinSpec] = field(default_factory=list)

    def pure_toz(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for c in self.coins:
            if c.metal and c.pure_toz is not None:
                out[c.metal] = out.get(c.metal, Decimal(0)) + c.pure_toz * c.quantity
        return out


def pure(weight_g: Decimal, fineness: Decimal) -> Decimal:
    return (weight_g / TROY * fineness).quantize(Q, rounding=ROUND_HALF_UP)


def _coin(year: int, mark: str | None, denom: str, name: str, series: str | None, silver: tuple[str, str] | None = None,
          composition: str | None = None) -> SetCoinSpec:
    # the 1975 and 1976 sets hold the dual-dated Bicentennial quarter, half and dollar
    dual = year in (1975, 1976) and denom in ("25c", "50c", "$1")
    date = f"{'1776-1976' if dual else year}-{mark}" if mark else str(year)
    label = f"{date} {'Bicentennial ' if dual else ''}{name}"
    if silver:
        w, f = Decimal(silver[0]), Decimal(silver[1])
        pct = ".999" if f >= Decimal("0.999") else f"{(f * 100).normalize():f}%"
        return SetCoinSpec(label, denom, year, mark, series, 1, f"{pct} silver", w, "Ag", f, pure(w, f))
    # 1982 proof cents are all the copper alloy (the "weigh it" note is for circulation strikes)
    base = base_metals.lookup(US, denom, 1981 if (denom, year) == ("1c", 1982) else year, mark, series)
    return SetCoinSpec(label, denom, year, mark, series, 1, composition or (base.composition if base else None),
                       base.weight_g if base else None)


def _quarters(year: int) -> list[tuple[str, str]]:
    """(name on the coin, series) of each quarter design struck that year."""
    if year in STATE_QUARTERS:
        return [(n, "50 State Quarters") for n in STATE_QUARTERS[year]]
    if year == 2009:
        return [(n, "DC and U.S. Territories") for n in TERRITORY_QUARTERS]
    if year in ATB_QUARTERS:
        return [(n, "America the Beautiful") for n in ATB_QUARTERS[year]]
    if year == 2021:
        return list(QUARTERS_2021)
    if year in WOMEN_QUARTERS:
        return [(n, "American Women") for n in WOMEN_QUARTERS[year]]
    return [("Washington", "Washington")]


def _half_series(year: int) -> str:
    return "Walking Liberty" if year <= 1947 else "Franklin" if year <= 1963 else "Kennedy"


def _dollars(year: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if 1973 <= year <= 1978:
        out.append(("Eisenhower dollar", "Eisenhower"))
    elif 1979 <= year <= 1981:
        out.append(("Susan B. Anthony dollar", "Susan B. Anthony"))
    if year in PRESIDENTS:
        out += [(f"{p} Presidential dollar", "Presidential") for p in PRESIDENTS[year]]
    if 2000 <= year <= 2008:
        out.append(("Sacagawea dollar", "Sacagawea"))
    elif year >= 2009:
        out.append(("Native American dollar", "Native American"))
    return out


def _quarter_series_name(year: int) -> str:
    if year in STATE_QUARTERS:
        return "50 State Quarters"
    if year == 2009:
        return "DC and U.S. Territories Quarters"
    if year in ATB_QUARTERS:
        return "America the Beautiful Quarters"
    if year in WOMEN_QUARTERS:
        return "American Women Quarters"
    return "Quarters"


def contents(year: int | None, kind: str | None, quarters_only: bool = False) -> SetSpec | None:
    """The coins in a US Mint proof set of this year and kind, or None when this list doesn't cover it."""
    if year is None or kind not in ("proof", "silver_proof"):
        return None
    silver_set = kind == "silver_proof"
    if silver_set and not 1992 <= year <= 2025:
        return None
    if not silver_set and not (1936 <= year <= 1941 or 1950 <= year <= 2025):
        return None
    if not silver_set and 1965 <= year <= 1967:
        return None  # no proof sets: Special Mint Sets those years
    mark = "S" if year >= 1968 else None  # Philadelphia proofs carried no mint mark
    silver_era = year <= 1964
    spec = (SILVER_999 if year >= 2019 else SILVER_90) if (silver_set or silver_era) else None

    def silver(denom: str) -> tuple[str, str] | None:
        if spec:
            return spec[denom]
        return HALF_40 if denom == "50c" and 1968 <= year <= 1970 else None

    quarters = [_coin(year, mark, "25c", f"{n} quarter", s, silver("25c")) for n, s in _quarters(year)]
    if quarters_only:
        if year < 1999 or year == 2021:
            return None
        name = f"{_quarter_series_name(year)} {'Silver ' if silver_set else ''}Proof Set"
        return SetSpec(name, kind, year, mark, quarters)

    coins: list[SetCoinSpec] = []
    if year == 2009:
        coins += [_coin(year, mark, "1c", f"Lincoln cent, {n}", "Lincoln Bicentennial", composition=CENT_2009) for n in CENTS_2009]
    else:
        cent = "Lincoln Wheat" if year <= 1958 else "Lincoln Memorial" if year <= 2008 else "Lincoln Shield"
        coins.append(_coin(year, mark, "1c", "Lincoln cent", cent))
    if year in NICKELS:
        coins += [_coin(year, mark, "5c", f"Jefferson nickel, {n}", "Westward Journey") for n in NICKELS[year]]
    else:
        coins.append(_coin(year, mark, "5c", "Buffalo nickel" if year <= 1937 else "Jefferson nickel", "Buffalo" if year <= 1937 else "Jefferson"))
    dime = "Mercury" if year <= 1945 else "Roosevelt"
    coins.append(_coin(year, mark, "10c", f"{dime} dime", dime, silver("10c")))
    coins += quarters
    half = _half_series(year)
    coins.append(_coin(year, mark, "50c", f"{half} half dollar", half, silver("50c")))
    coins += [_coin(year, mark, "$1", n, s) for n, s in _dollars(year)]
    return SetSpec("Silver Proof Set" if silver_set else "Proof Set", kind, year, mark, coins)
