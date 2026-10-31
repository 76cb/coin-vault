"""PCGS Public API (https://www.pcgs.com/publicapi/documentation; Swagger at
https://api.pcgs.com/publicapi/swagger/docs/v1, checked 2026-10-31).

GET https://api.pcgs.com/publicapi/coindetail/GetCoinFactsByCertNo/{certNo}
GET https://api.pcgs.com/publicapi/coindetail/GetCoinFactsByGrade?PCGSNo=&GradeNo=&PlusGrade=   (all three required)
GET https://api.pcgs.com/publicapi/coindetail/GetCoinFactsByBarcode?barcode=&gradingService=      (PCGS or NGC)
    Authorization: bearer <access token>   (token generated with the owner's PCGS login)
    By grade and by barcode return the same fields (CoinFactsByGradeModel, CoinFactsByBarcodeModel); by grade
    has no cert number.
    -> CoinFactsModel: PCGSNo, CertNo, Name, Year, Denomination, Mintage, MintMark, MintLocation, MetalContent,
       Diameter, Edge, Weight, Country, Grade, Designation, PriceGuideValue, Population, PopHigher, CoinFactsLink,
       Designer, Images [{Thumbnail, Fullsize}], CoinFactsNotes, MajorVariety, MinorVariety, DieVariety,
       AuctionList, SeriesName, Category, HasTrueViewImage, ImageReady, IsNFCSecure, IsValidRequest, ServerMessage
Status: 200 even when there's no data (check IsValidRequest / ServerMessage); 500 usually means bad credentials.
Daily limit: 1,000 calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import ProviderError

BASE = "https://api.pcgs.com/publicapi"
CERT_RE = re.compile(r"^\d{6,10}$")
METAL_NAMES = {"gold": "Au", "silver": "Ag", "platinum": "Pt", "palladium": "Pd"}


@dataclass
class PcgsCoin:
    cert_no: str | None
    pcgs_no: str | None
    name: str | None
    year: int | None
    denomination: str | None
    mint_mark: str | None
    country: str | None
    grade: str | None
    designation: str | None
    metal_content: str | None
    weight_g: Decimal | None
    diameter_mm: Decimal | None
    price_guide: Decimal | None
    population: int | None
    pop_higher: int | None
    coinfacts_link: str | None
    series: str | None
    category: str | None
    variety: str | None
    images: list[dict] = field(default_factory=list)


def _dec(v) -> Decimal | None:
    if v in (None, "", 0, 0.0):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d > 0 else None


def parse_metal(text: str | None) -> tuple[str, Decimal] | None:
    """'90% Silver, 10% Copper' -> ('Ag', 0.900); '99.9% Silver' -> ('Ag', 0.999); clad or base metal -> None."""
    if not text:
        return None
    best = None
    for pct, name in re.findall(r"(\d+(?:\.\d+)?)\s*%\s*(gold|silver|platinum|palladium)", text, re.I):
        frac = (Decimal(pct) / 100).quantize(Decimal("0.0001"))
        if best is None or frac > best[1]:
            best = (METAL_NAMES[name.lower()], frac)
    if best is None:
        m = re.search(r"\.(\d{3,4})\s*(?:fine\s*)?(gold|silver|platinum|palladium)", text, re.I)
        if m:
            best = (METAL_NAMES[m.group(2).lower()], Decimal("0." + m.group(1)))
    return best


GRADE_RE = re.compile(r"^\s*(?:MS|PR|PF|SP|AU|XF|EF|VF|F|VG|G|AG|FR|PO|P)?\s*-?\s*(\d{1,2})\s*(\+)?\s*$", re.I)


def parse_grade(text: str) -> tuple[int, bool]:
    """'MS65' -> (65, False); '64+' -> (64, True); 'PR 69' -> (69, False). PCGS's number already says proof or not."""
    m = GRADE_RE.match(text or "")
    if not m or not 1 <= int(m.group(1)) <= 70:
        raise ProviderError("Give a grade from 1 to 70, like MS65 or 64+", cost=0)
    return int(m.group(1)), bool(m.group(2))


def _get(client: httpx.Client, token: str, path: str, params: dict | None, what: str) -> dict:
    try:
        r = client.get(f"{BASE}/coindetail/{path}", params=params, headers={"Authorization": f"bearer {token}"})
    except httpx.HTTPError as exc:
        raise ProviderError(f"{type(exc).__name__} calling PCGS", cost=0) from exc
    if r.status_code in (401, 403, 500):
        # PCGS answers 500 for invalid credentials
        raise ProviderError(f"PCGS refused the token (HTTP {r.status_code}); generate a new one on the PCGS Public API page", r.status_code, cost=1)
    if r.status_code == 429:
        raise ProviderError("PCGS daily limit reached (1,000 calls); it resets tomorrow", 429, cost=0)
    if r.status_code == 204:
        raise ProviderError(f"PCGS returned no data for {what}", 204, cost=1)
    if r.status_code != 200:
        raise ProviderError(f"PCGS returned HTTP {r.status_code}", r.status_code, cost=1)
    try:
        d = r.json()
    except ValueError as exc:
        raise ProviderError("PCGS sent something that isn't JSON", r.status_code, cost=1) from exc
    if not isinstance(d, dict) or not d.get("IsValidRequest"):
        msg = (d or {}).get("ServerMessage") if isinstance(d, dict) else None
        raise ProviderError(f"PCGS: {msg or 'no data found'}", r.status_code, cost=1)
    return d


def _coin(d: dict, cert: str | None = None) -> PcgsCoin:
    year = d.get("Year")
    return PcgsCoin(
        cert_no=str(d.get("CertNo") or cert or "") or None,
        pcgs_no=str(d["PCGSNo"]) if d.get("PCGSNo") else None,
        name=d.get("Name"),
        year=int(year) if isinstance(year, int) and year > 0 else None,
        denomination=d.get("Denomination") or None,
        mint_mark=d.get("MintMark") or None,
        country=d.get("Country") or None,
        grade=d.get("Grade") or None,
        designation=d.get("Designation") or None,
        metal_content=d.get("MetalContent") or None,
        weight_g=_dec(d.get("Weight")),
        diameter_mm=_dec(d.get("Diameter")),
        price_guide=_dec(d.get("PriceGuideValue")),
        population=d.get("Population"),
        pop_higher=d.get("PopHigher"),
        coinfacts_link=d.get("CoinFactsLink") or None,
        series=d.get("SeriesName") or None,
        category=d.get("Category") or None,
        variety=" ".join(x for x in [d.get("MajorVariety"), d.get("MinorVariety"), d.get("DieVariety")] if x) or None,
        images=[{"thumbnail": i.get("Thumbnail"), "fullsize": i.get("Fullsize")} for i in (d.get("Images") or []) if isinstance(i, dict)],
    )


def lookup_cert(client: httpx.Client, token: str, cert_no: str) -> PcgsCoin:
    cert = re.sub(r"\D", "", cert_no or "")
    if not CERT_RE.match(cert):
        raise ProviderError("A PCGS cert number is 6 to 10 digits", cost=0)
    return _coin(_get(client, token, f"GetCoinFactsByCertNo/{cert}", None, "that cert number"), cert)


def lookup_grade(client: httpx.Client, token: str, pcgs_no: str, grade: str) -> PcgsCoin:
    """A coin type at a grade: CoinFacts and the price guide value, without a cert (e.g. a raw or NGC coin)."""
    num = re.sub(r"\D", "", pcgs_no or "")
    if not 1 <= len(num) <= 7:
        raise ProviderError("A PCGS number is up to 7 digits, like 9801", cost=0)
    grade_no, plus = parse_grade(grade)
    params = {"PCGSNo": num, "GradeNo": grade_no, "PlusGrade": "true" if plus else "false"}
    return _coin(_get(client, token, "GetCoinFactsByGrade", params, f"PCGS #{num} in grade {grade_no}{'+' if plus else ''}"))


def lookup_barcode(client: httpx.Client, token: str, barcode: str, service: str) -> PcgsCoin:
    """The barcode text from a PCGS or NGC holder's label."""
    text = (barcode or "").strip()
    if not 4 <= len(text) <= 60 or not re.fullmatch(r"[\w\-./ ]+", text):
        raise ProviderError("That doesn't look like the text of a holder's barcode", cost=0)
    if service not in ("PCGS", "NGC"):
        raise ProviderError("The grading service is PCGS or NGC", cost=0)
    return _coin(_get(client, token, "GetCoinFactsByBarcode", {"barcode": text, "gradingService": service}, "that barcode"))
