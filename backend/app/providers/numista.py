"""Numista API v3 (OpenAPI spec 3.36.4, supplied by the owner from en.numista.com/api/doc, 2026-10-31).

Base https://api.numista.com/v3, header "Numista-API-Key: <key>". Used here:
    GET /types?q=&year=&object_type=&page=&count=(<=100)&lang=en       -> {count, types:[{id, title, issuer{code,name},
                                                                            min_year, max_year, obverse_thumbnail, ...}]}
    GET /types/{type_id}?lang=en      -> type: url, title, issuer, value{text, numeric_value, currency}, composition{text},
                                         weight (g), size (mm), obverse/reverse{picture, thumbnail}, references[{catalogue{code}, number}],
                                         min_year, max_year, series, commemorated_topic, ruler[]
    GET /types/{type_id}/issues       -> [{id, is_dated, year, gregorian_year, mint_letter, mintage, comment, min_year, max_year}]
    GET /types/{type_id}/issues/{issue_id}/prices?currency=USD -> {currency, prices:[{grade: g|vg|f|vf|xf|au|unc, price}]}
Errors: 400, 401 (invalid or missing key), 404, 429 (too many simultaneous requests, or the monthly quota reached);
body {"error_message": "..."}. Quota: set by the owner's plan (2,000 requests a calendar month on theirs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import ProviderError

BASE = "https://api.numista.com/v3"
COINS_OBJECT_TYPE = 147  # "Coins" (the spec's example for searching coins only)
METALS = {"gold": "Au", "silver": "Ag", "platinum": "Pt", "palladium": "Pd"}
GRADES = ("g", "vg", "f", "vf", "xf", "au", "unc")
GRADE_NAMES = {"g": "G", "vg": "VG", "f": "F", "vf": "VF", "xf": "XF", "au": "AU", "unc": "Unc"}


@dataclass
class NumistaType:
    id: int
    url: str | None
    title: str
    issuer: str | None
    issuer_code: str | None
    min_year: int | None
    max_year: int | None
    denomination: str | None
    currency: str | None
    composition: str | None
    weight_g: Decimal | None
    size_mm: Decimal | None
    series: str | None
    references: list[str] = field(default_factory=list)  # "KM# 2", "Schön# 2"
    obverse: str | None = None
    reverse: str | None = None
    obverse_thumb: str | None = None
    reverse_thumb: str | None = None


@dataclass
class NumistaIssue:
    id: int
    year: int | None
    gregorian_year: int | None
    mint_letter: str | None
    mintage: int | None
    comment: str | None


def _dec(v) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return None
    return d if d.is_finite() and d > 0 else None


def parse_composition(text: str | None) -> tuple[str, Decimal] | None:
    """Numista's composition text -> (metal, fineness) for precious metal, else None.

    'Silver (.925) (.925 silver .075 copper)' -> ('Ag', 0.925); 'Gold (.900)' -> ('Au', 0.900);
    'Silver (.999)' -> ('Ag', 0.999); 'Bimetallic: ...' or 'Copper-nickel' -> None.
    """
    if not text:
        return None
    low = text.lower()
    if low.startswith(("bimetallic", "silver plated", "gold plated", "silver-plated", "gold-plated", "silver clad", "billon")) and "(." not in low:
        return None
    m = re.match(r"\s*(gold|silver|platinum|palladium)\b[^(]*\(\s*(0?\.\d{2,4}|\d{3,4}(?:\.\d)?\s*‰?)\s*\)", low)
    if not m:
        return None
    raw = m.group(2).replace("‰", "").strip()
    try:
        fine = Decimal(raw) if raw.startswith(("0.", ".")) else Decimal(raw) / 1000
    except InvalidOperation:
        return None
    if not Decimal(0) < fine <= 1:
        return None
    return METALS[m.group(1)], fine.quantize(Decimal("0.0001"))


class Numista:
    def __init__(self, client: httpx.Client, api_key: str):
        self.client = client
        self.key = api_key

    def _get(self, path: str, params: dict | None = None):
        try:
            r = self.client.get(BASE + path, params={"lang": "en", **(params or {})}, headers={"Numista-API-Key": self.key})
        except httpx.HTTPError as exc:
            raise ProviderError(f"{type(exc).__name__} calling Numista", cost=0) from exc
        try:
            data = r.json()
        except ValueError:
            data = None
        said = data.get("error_message") if isinstance(data, dict) else None
        if r.status_code == 401:
            raise ProviderError("Numista refused the API key (HTTP 401); check it on your Numista API page", 401, cost=1)
        if r.status_code == 429:
            raise ProviderError(f"Numista: {said or 'too many requests, or this month’s quota is used up'} (HTTP 429)", 429, cost=0)
        if r.status_code == 404:
            raise ProviderError(f"Numista: {said or 'not found'}", 404, cost=1)
        if r.status_code != 200 or data is None:
            raise ProviderError(f"Numista returned HTTP {r.status_code}{': ' + said if said else ''}", r.status_code, cost=1)
        return data

    def search(self, q: str, year: str | None = None, count: int = 20) -> tuple[int, list[dict]]:
        params: dict = {"q": q, "object_type": COINS_OBJECT_TYPE, "count": min(max(count, 1), 50), "order": "relevance"}
        if year:
            params["year"] = year
        d = self._get("/types", params)
        out = []
        for t in d.get("types") or []:
            issuer = t.get("issuer") or {}
            out.append({
                "id": t.get("id"), "title": t.get("title"), "issuer": issuer.get("name"), "min_year": t.get("min_year"),
                "max_year": t.get("max_year"), "obverse_thumbnail": t.get("obverse_thumbnail"),
                "reverse_thumbnail": t.get("reverse_thumbnail"),
            })
        return int(d.get("count") or 0), [t for t in out if isinstance(t["id"], int)]

    def type(self, type_id: int) -> dict:
        return self._get(f"/types/{int(type_id)}")

    def issues(self, type_id: int) -> list[dict]:
        d = self._get(f"/types/{int(type_id)}/issues")
        return d if isinstance(d, list) else []

    def prices(self, type_id: int, issue_id: int, currency: str) -> tuple[str, dict[str, Decimal]]:
        d = self._get(f"/types/{int(type_id)}/issues/{int(issue_id)}/prices", {"currency": currency})
        prices = {}
        for p in d.get("prices") or []:
            v = _dec(p.get("price"))
            if p.get("grade") in GRADES and v is not None:
                prices[p["grade"]] = v
        return str(d.get("currency") or currency), prices


def to_type(d: dict) -> NumistaType:
    issuer = d.get("issuer") or {}
    value = d.get("value") or {}
    obv = d.get("obverse") or {}
    rev = d.get("reverse") or {}
    refs = []
    for ref in d.get("references") or []:
        code = (ref.get("catalogue") or {}).get("code")
        if code and ref.get("number"):
            refs.append(f"{code}# {ref['number']}")
    return NumistaType(
        id=int(d["id"]), url=d.get("url"), title=d.get("title") or "", issuer=issuer.get("name"), issuer_code=issuer.get("code"),
        min_year=d.get("min_year"), max_year=d.get("max_year"), denomination=value.get("text"),
        currency=(value.get("currency") or {}).get("name"), composition=(d.get("composition") or {}).get("text"),
        weight_g=_dec(d.get("weight")), size_mm=_dec(d.get("size")), series=d.get("series"), references=refs,
        obverse=obv.get("picture"), reverse=rev.get("picture"), obverse_thumb=obv.get("thumbnail"), reverse_thumb=rev.get("thumbnail"),
    )


def to_issues(rows: list[dict]) -> list[NumistaIssue]:
    out = []
    for r in rows:
        if not isinstance(r.get("id"), int):
            continue
        out.append(NumistaIssue(
            id=r["id"], year=r.get("year"), gregorian_year=r.get("gregorian_year") or r.get("min_year"),
            mint_letter=r.get("mint_letter") or None, mintage=r.get("mintage"), comment=r.get("comment") or None,
        ))
    return out


def grade_for(sheldon: int | None, grade_text: str | None) -> str | None:
    """Numista's grade band for a coin's grade: Sheldon 60+ is Unc, 50-58 AU, 40-45 XF, 20-35 VF, 12-15 F, 8-10 VG, 4-6 G."""
    if sheldon is None and grade_text:
        m = re.search(r"(\d{1,2})", grade_text)
        sheldon = int(m.group(1)) if m else None
        if sheldon is None:
            t = grade_text.strip().lower()
            for g in ("unc", "au", "xf", "ef", "vf", "vg", "f", "g"):
                if t.startswith(g):
                    return "xf" if g == "ef" else g
            return None
    if sheldon is None:
        return None
    for floor, g in ((60, "unc"), (50, "au"), (40, "xf"), (20, "vf"), (12, "f"), (8, "vg"), (1, "g")):
        if sheldon >= floor:
            return g
    return None


_GRADE_IN_TEXT = re.compile(r"(?<![A-Za-z])(MS|PR|PF|SP|AU|XF|EF|VF|VG|AG|FR|PO|F|G)[\s-]?(\d{1,2})\b")


def grade_in_text(text: str) -> tuple[str, int] | None:
    """A Sheldon grade written in free text ("PCGS MS70" -> ("MS70", 70)); None when there isn't one."""
    for m in _GRADE_IN_TEXT.finditer(text or ""):
        n = int(m.group(2))
        if 1 <= n <= 70:
            return f"{m.group(1).upper()}{n}", n
    return None
