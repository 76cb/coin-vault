"""Looking at photos with a local vision model (through Ollama): identifying a piece, reading a grading holder's
label, suggesting a grade for a raw coin, and spotting pieces you already have. Photos only ever go to the AI
server the admin set up on your own network."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import CoinDetails, Item, Photo
from app.models import UploadFile as UploadFileRow
from app.providers import ollama
from app.services import barcodes, photo_edit, storage
from app.services.coin_words import US, canonical_country, denom_key, us_denom
from app.services.images import phash_distance

MAX_PHOTOS = 4
PHOTO_EDGE = 1536  # long side sent to the model: enough to read a date or a label, small enough to stay quick
ROLE_WORDS = {
    "obverse": "the obverse (front)", "reverse": "the reverse (back)", "edge": "the edge",
    "slab_front": "the front of the grading holder, with its label", "slab_back": "the back of the grading holder",
    "other": "another view",
}
ROLE_ORDER = ["obverse", "reverse", "slab_front", "slab_back", "edge", "other"]
SERVICES = ["PCGS", "NGC", "ANACS", "ICG", "CACG", "PMG", "other", ""]


class AiNotSet(Exception):
    pass


class PhotoMissing(Exception):
    pass


def configured(db: Session) -> tuple[str, str] | None:
    from app.services.providers import get_system

    url, model = str(get_system(db, "ai_url") or ""), str(get_system(db, "ai_model") or "")
    return (url, model) if url and model else None


def _settings(db: Session) -> tuple[str, str]:
    s = configured(db)
    if s is None:
        raise AiNotSet("The AI server isn't set up yet. An admin can add it in Settings, under AI.")
    return s


# --- Photos ------------------------------------------------------------------------------------


@dataclass
class Source:
    sha256: str
    role: str
    storage_key: str
    edits: dict[str, Any] | None
    phash: str | None


def sources(db: Session, owner_id: int, refs: list[tuple[str, str]], item_id: int | None) -> list[Source]:
    """Each photo by its file hash: the copy on `item_id` when it's there (with its edits, so a crop to the
    coin helps), else an edited copy on any of your items, else the file as uploaded."""
    out = []
    for sha, role in refs:
        photos = list(db.scalars(
            select(Photo).join(Item, Item.id == Photo.item_id)
            .where(Item.owner_id == owner_id, Photo.sha256 == sha).order_by(Photo.id)
        ))
        photo = next((p for p in photos if p.item_id == item_id), None) or next((p for p in photos if p.edits), None) or (photos[0] if photos else None)
        if photo is not None:
            out.append(Source(sha, role, photo.storage_key, photo.edits or None, photo.phash))
            continue
        up = db.scalar(select(UploadFileRow).where(UploadFileRow.owner_id == owner_id, UploadFileRow.sha256 == sha).limit(1))
        if up is None:
            raise PhotoMissing("One of those photos isn't in your library")
        out.append(Source(sha, role, up.storage_key, None, up.phash))
    out.sort(key=lambda s: ROLE_ORDER.index(s.role) if s.role in ROLE_ORDER else len(ROLE_ORDER))
    return out[:MAX_PHOTOS]


def jpeg_for_model(src: Source) -> bytes:
    with Image.open(storage.path_for(src.storage_key)) as original:
        original.draft("RGB", (PHOTO_EDGE * 2, PHOTO_EDGE * 2))
        if src.edits:
            img = photo_edit.render(original, src.edits, PHOTO_EDGE)
        else:
            img = ImageOps.exif_transpose(original)
            img.thumbnail((PHOTO_EDGE, PHOTO_EDGE), Image.Resampling.LANCZOS)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (128, 128, 128))  # a clear cut-out sits on neutral grey
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _photo_list(srcs: list[Source]) -> str:
    return "\n".join(f"Photo {i + 1} is {ROLE_WORDS.get(s.role, 'another view')}." for i, s in enumerate(srcs))


def _ask(db: Session, system: str, prompt: str, srcs: list[Source], schema: dict) -> ollama.ChatResult:
    url, model = _settings(db)
    images = [jpeg_for_model(s) for s in srcs]
    with ollama.client(ollama.CHAT_SECONDS) as c:
        return ollama.chat_json(c, url, model, system, prompt, images, schema)


def _s(v: Any, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


# --- Identifying -------------------------------------------------------------------------------

IDENTIFY_SYSTEM = (
    "You identify coins, bullion, bars and banknotes from photos for a collector's inventory. Read what is actually "
    "struck or printed: legends, dates, mint marks, denominations, and any grading holder's label. Never guess a date, "
    "mint mark or number you can't read; leave it empty instead. Don't judge whether a piece is genuine: photos can't show "
    "that, and crowded or run-together lettering is usually how the design was engraved. Answer only with the JSON asked for."
)

IDENTIFY_PROMPT = """{photos}

Identify this piece. Fill in:
- kind: "coin" (a circulating or collector coin), "bullion" (a bullion coin or round sold for its metal, like an American Silver Eagle or a Maple Leaf), "bar", "banknote", "goldback" (a Goldback gold note: give its state or series and its denomination in the title, like "2019 Utah Goldback 5") or "other".
- country: the issuing country in English, like "United States". Empty for a private round or bar.
- denomination: as written on the piece, in English, like "Quarter Dollar", "One Cent", "1 Dollar", "50 Pence". Empty for a bar or round.
- year: the date on the piece; 0 if you can't read one.
- mint_mark: the mint mark letters exactly as struck (like D, S, O, CC, W). Empty if there is none or you can't see it. Never write P unless a P is visible.
- series: the design's usual collector name, like "Washington Quarter", "Morgan Dollar", "Lincoln Wheat Cent", "American Silver Eagle".
- metal: the main metal.
- weight_text: any weight and fineness marked on the piece, like "1 OZ. FINE SILVER" or "10 g 999.9"; empty if none.
- title: a short listing-style title, date first, the way a dealer lists it: like "1956 D Washington Quarter" or "2021 1 oz American Silver Eagle Type 2 PCGS MS70". Put a grading service and grade in it only when the piece is in a grading holder. When it is in a holder, the label names the piece, so take the title from the label even if the coin itself is too small to read: like "2027-P Australia $5 Gold Lunar Year of the Goat NGC MS69". NGC labels put the metal before the dollar sign: G$5 is a gold $5, S$1 a silver $1, P$15 a platinum $15.
- holder: when the piece is sealed in a grading holder (a slab), copy from its label: service; grade exactly as printed (like "MS65", "PR69 DCAM", "AU Details"); cert_number; pcgs_number (only on PCGS labels); label_text (all the label's text, each line as printed). On a PCGS label the numbers line reads like "7411.67/48872051": the PCGS coin number (7411), a dot, the grade (67), a slash, then the cert number (48872051). The cert number is only the part after the slash. An NGC cert number looks like "8698301-036". When it isn't in a holder: in_holder false and the rest empty.
- confidence: "high" only when the date, denomination and design are all clearly visible.
- notes: one or two short sentences on anything you couldn't read or aren't sure of. Empty if nothing."""

IDENTIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["coin", "bullion", "bar", "banknote", "goldback", "other"]},
        "country": {"type": "string"},
        "denomination": {"type": "string"},
        "year": {"type": "integer"},
        "mint_mark": {"type": "string"},
        "series": {"type": "string"},
        "metal": {"type": "string", "enum": ["gold", "silver", "platinum", "palladium", "copper", "nickel", "clad", "other", "unknown"]},
        "weight_text": {"type": "string"},
        "title": {"type": "string"},
        "holder": {
            "type": "object",
            "properties": {
                "in_holder": {"type": "boolean"},
                "service": {"type": "string", "enum": SERVICES},
                "grade": {"type": "string"},
                "cert_number": {"type": "string"},
                "pcgs_number": {"type": "string"},
                "label_text": {"type": "string"},
            },
            "required": ["in_holder", "service", "grade", "cert_number", "pcgs_number", "label_text"],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["kind", "country", "denomination", "year", "mint_mark", "series", "metal", "weight_text", "title", "holder", "confidence", "notes"],
}

METAL_CODES = {"gold": "Au", "silver": "Ag", "platinum": "Pt", "palladium": "Pd"}


@dataclass
class Holder:
    service: str | None = None
    grade: str | None = None
    cert_number: str | None = None
    pcgs_number: str | None = None
    label_text: str | None = None


@dataclass
class Identified:
    kind: str
    country: str | None
    denomination: str | None
    year: int | None
    mint_mark: str | None
    series: str | None
    metal: str | None  # Au, Ag, Pt, Pd, or None
    weight_text: str | None
    title: str
    holder: Holder | None
    confidence: str
    notes: str | None
    seconds: float = 0.0
    load_seconds: float = 0.0
    barcodes: list[dict[str, str]] = field(default_factory=list)


def _cert(text: str) -> str | None:
    t = re.sub(r"[^0-9-]", "", text or "")
    return t if 6 <= len(t.replace("-", "")) <= 20 else None


# a PCGS label's numbers line: PCGS coin number . grade (maybe with +) / cert number
PCGS_LINE = re.compile(r"\b(\d{2,6})\s*\.\s*(\d{1,2})\+?\s*/\s*(\d{7,10})\b")


def _pcgs_numbers(*texts: str) -> tuple[str, str] | None:
    """(PCGS number, cert number) from a label's "7411.67/48872051" line, wherever the model put it."""
    for t in texts:
        m = PCGS_LINE.search(t or "")
        if m:
            return m.group(1), m.group(3)
    return None


def parse_identified(d: dict[str, Any]) -> Identified:
    kind = d.get("kind") if d.get("kind") in ("coin", "bullion", "bar", "banknote", "goldback", "other") else "coin"
    try:
        year = int(d.get("year") or 0)
    except (TypeError, ValueError):
        year = 0
    year = year if 1 <= year <= 2100 else None
    mint = _s(d.get("mint_mark"), 10).upper().strip(".") or None
    if mint and not re.fullmatch(r"[A-Z]{1,3}", mint):
        mint = None
    h = d.get("holder") if isinstance(d.get("holder"), dict) else {}
    holder = None
    if h.get("in_holder"):
        service = _s(h.get("service"), 10)
        holder = Holder(
            service=service if service and service != "other" else None,
            grade=_s(h.get("grade"), 40) or None,
            cert_number=_cert(_s(h.get("cert_number"), 40)),
            pcgs_number=(re.sub(r"\D", "", _s(h.get("pcgs_number"), 20)) or None) if service == "PCGS" else None,
            label_text=_s(h.get("label_text"), 600) or None,
        )
        if service == "PCGS":
            nums = _pcgs_numbers(_s(h.get("label_text"), 600), _s(h.get("cert_number"), 40))
            if nums:
                holder.pcgs_number, holder.cert_number = nums
            elif holder.cert_number and holder.pcgs_number and len(holder.cert_number) > 10:
                # the whole line run together ("74116748872051"): PCGS number and grade first, then the cert
                digits = holder.cert_number.replace("-", "")
                g = re.sub(r"\D", "", holder.grade or "")
                lead = holder.pcgs_number + g
                if g and digits.startswith(lead) and 7 <= len(digits) - len(lead) <= 10:
                    holder.cert_number = digits[len(lead):]
    title = _s(d.get("title"), 200)
    if not title:
        title = " ".join(str(x) for x in (year, mint, _s(d.get("series")) or _s(d.get("denomination"))) if x)
    return Identified(
        kind=kind,
        country=canonical_country(_s(d.get("country"), 80)) or _s(d.get("country"), 80) or None,
        denomination=_s(d.get("denomination"), 80) or None,
        year=year,
        mint_mark=mint,
        series=_s(d.get("series"), 120) or None,
        metal=METAL_CODES.get(_s(d.get("metal")).lower()),
        weight_text=_s(d.get("weight_text"), 120) or None,
        title=title or "Unidentified piece",
        holder=holder,
        confidence=d.get("confidence") if d.get("confidence") in ("high", "medium", "low") else "low",
        notes=_s(d.get("notes"), 500) or None,
    )


def read_barcodes(srcs: list[Source]) -> list[dict[str, str]]:
    """Barcodes on any of the photos (a holder's label), read on this server."""
    found: dict[str, dict[str, str]] = {}
    for s in srcs:
        try:
            for b in barcodes.read(storage.path_for(s.storage_key).read_bytes()):
                found.setdefault(b["text"], b)
        except (ValueError, OSError):
            continue
    return list(found.values())


def identify(db: Session, srcs: list[Source]) -> Identified:
    r = _ask(db, IDENTIFY_SYSTEM, IDENTIFY_PROMPT.format(photos=_photo_list(srcs)), srcs, IDENTIFY_SCHEMA)
    out = parse_identified(r.data)
    out.seconds, out.load_seconds = r.seconds, r.load_seconds
    out.barcodes = read_barcodes(srcs)
    return out


def listing_title(i: Identified) -> str:
    """The text handed to the title reader: the model's own title, with the holder's grade added when it left it out."""
    t = i.title
    if i.holder and i.holder.service and i.holder.service not in t:
        t = f"{t} {i.holder.service} {i.holder.grade or ''}".strip()
    return t


# --- Grading -----------------------------------------------------------------------------------

GRADE_SYSTEM = (
    "You are an experienced coin grader using the Sheldon 1-70 scale and US grading standards. You judge wear on the "
    "high points, luster, strike, marks and eye appeal, and you say plainly when photos can't settle something. Answer "
    "only with the JSON asked for."
)

GRADE_PROMPT = """{photos}{context}

Estimate the grade of this raw (not slabbed) coin from its photos. Photos can hide or exaggerate wear and marks, so give a range, not one grade, but keep it tight: two neighbouring grades on the usual scale (like VF20 and VF30, or MS62 and MS63), wider only when the photos really can't tell.

Grade the wear and surfaces only. Don't judge whether the coin is genuine: photos can't show that, and lettering that looks crowded or run together (like IN GOD WE TRUST on a Washington quarter) is usually just how the design was engraved. Don't call anything counterfeit, fake or an error.

For a coin with no wear (mint state), the grade comes from its marks, luster and strike, judged against coins of its kind. First list each mark you can actually see and where it is. As a guide: MS70, no marks even under magnification; MS69, one or two tiny marks; MS67 to MS68, a few small marks away from the main design; MS65 to MS66, several small marks or one you notice straight away; MS63 to MS64, many marks or some in prominent places; MS60 to MS62, heavy marks or dull, broken luster. Modern coins (from about 1980) and bullion coins usually leave the mint at MS67 to MS70, so grade one of those lower only for marks you can clearly see.

Fill in:
- low and high: Sheldon grades with their prefix, like "VF20" and "VF30", or "MS62" and "MS64". Prefixes: P, FR, AG, G, VG, F, VF, EF, AU, MS, and PR for proofs.
- summary: one sentence on the grade, in plain words.
- wear: what the high points show.
- surfaces: luster, marks, toning.
- marks: each mark you can clearly see in these photos, with where it is, like "small tick on the cheek". Name places by what is actually on this coin; never mention design elements you can't see. Small marks are usually too small to see in a photo, so an empty list is the normal answer; don't guess.
- problems: damage that would make it a "Details" grade (cleaning, scratches, rim damage, corrosion, holes, tooling). An empty list if you see none.
- photo_advice: what other photos would help settle the grade, like an angled shot to show luster. Empty if the photos are good enough."""

GRADE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "low": {"type": "string"},
        "high": {"type": "string"},
        "summary": {"type": "string"},
        "wear": {"type": "string"},
        "surfaces": {"type": "string"},
        "marks": {"type": "array", "items": {"type": "string"}},
        "problems": {"type": "array", "items": {"type": "string"}},
        "photo_advice": {"type": "string"},
    },
    "required": ["low", "high", "summary", "wear", "surfaces", "marks", "problems", "photo_advice"],
}

GRADE_RE = re.compile(r"\b(PO|P|FR|AG|G|VG|F|VF|EF|XF|AU|MS|PR|PF|SP)[\s-]?(\d{1,2})\b", re.I)
ADJECTIVE = [(1, "P"), (2, "FR"), (3, "AG"), (4, "G"), (8, "VG"), (12, "F"), (20, "VF"), (40, "EF"), (50, "AU"), (60, "MS")]


def _grade(text: str) -> tuple[str, int] | None:
    m = GRADE_RE.search(text or "")
    if not m or not 1 <= int(m.group(2)) <= 70:
        return None
    prefix = m.group(1).upper().replace("XF", "EF").replace("PF", "PR").replace("PO", "P")
    return f"{prefix}{int(m.group(2))}", int(m.group(2))


def _prefix_for(n: int, proof: bool) -> str:
    if proof and n >= 60:
        return "PR"
    return [p for lo, p in ADJECTIVE if n >= lo][-1]


@dataclass
class GradeGuess:
    low: str
    high: str
    low_number: int
    high_number: int
    summary: str
    wear: str | None
    surfaces: str | None
    marks: list[str]
    problems: list[str]
    photo_advice: str | None
    seconds: float = 0.0


def parse_grade(d: dict[str, Any]) -> GradeGuess:
    lo, hi = _grade(_s(d.get("low"))), _grade(_s(d.get("high")))
    if lo is None and hi is None:
        raise ollama.OllamaError("The model didn't give a grade on the 1-70 scale. Try again, or try clearer photos.")
    lo = lo or hi
    hi = hi or lo
    assert lo is not None and hi is not None
    if lo[1] > hi[1]:
        lo, hi = hi, lo
    proof = lo[0].startswith("PR") or hi[0].startswith("PR")
    # keep the model's prefix when it fits the number, else the standard one for it
    def tidy(g: tuple[str, int]) -> str:
        expected = _prefix_for(g[1], proof)
        return g[0] if re.sub(r"\d", "", g[0]) == expected else f"{expected}{g[1]}"
    problems = [_s(p, 200) for p in (d.get("problems") or []) if _s(p)][:8]
    marks = [_s(m, 200) for m in (d.get("marks") or []) if _s(m)][:12]
    return GradeGuess(
        low=tidy(lo), high=tidy(hi), low_number=lo[1], high_number=hi[1], summary=_s(d.get("summary"), 400),
        wear=_s(d.get("wear"), 600) or None, surfaces=_s(d.get("surfaces"), 600) or None, marks=marks, problems=problems,
        photo_advice=_s(d.get("photo_advice"), 400) or None,
    )


def grade_context(item: Item | None) -> str:
    """What the owner's record says the coin is, so it's judged against coins of its kind."""
    if item is None:
        return ""
    c = item.coin
    bits = [item.title]
    if c is not None:
        bits += [x for x in (c.product_line, c.series, c.country) if x and x.lower() not in item.title.lower()]
        if c.year and str(c.year) not in item.title:
            bits.append(f"dated {c.year}")
    kind = "a bullion coin" if item.item_type == "bullion" else "a coin"
    return f"\nThe owner's record says this is {kind}: {', '.join(bits)}."


def suggest_grade(db: Session, srcs: list[Source], item: Item | None = None) -> GradeGuess:
    prompt = GRADE_PROMPT.format(photos=_photo_list(srcs), context=grade_context(item))
    r = _ask(db, GRADE_SYSTEM, prompt, srcs, GRADE_SCHEMA)
    g = parse_grade(r.data)
    g.seconds = r.seconds
    return g


# --- Pieces you already have ---------------------------------------------------------------------


@dataclass
class Match:
    item: Item
    why: str


def _mint(country: str | None, mark: str | None) -> str:
    m = (mark or "").upper()
    return "" if country == US and m == "P" else m  # most Philadelphia coins carry no mark at all


def _same_denomination(country: str | None, a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    if country == US:
        return us_denom(a) is not None and us_denom(a) == us_denom(b)
    return denom_key(a) is not None and denom_key(a) == denom_key(b)


def _words(text: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 2 and w not in {"the", "and", "coin", "silver", "gold"}}


def same_coin(db: Session, owner_id: int, ident: dict[str, Any], exclude_item: int | None) -> list[Match]:
    """Items you hold that look like the same piece: same year and design (or denomination), same country and
    mint mark when both are known."""
    year = ident.get("year")
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    if year is None:
        return []
    country = canonical_country(ident.get("country")) or ident.get("country")
    rows = db.scalars(
        select(Item).join(CoinDetails, CoinDetails.item_id == Item.id)
        .where(Item.owner_id == owner_id, Item.deleted_at.is_(None), Item.status != "sold", CoinDetails.year == year)
        .options(selectinload(Item.coin), selectinload(Item.photos), selectinload(Item.condition))
    )
    out: list[Match] = []
    for it in rows:
        if it.id == exclude_item or it.coin is None:
            continue
        c = it.coin
        if country and c.country and (canonical_country(c.country) or c.country) != country:
            continue
        if _mint(country, ident.get("mint_mark")) != _mint(country, c.mint_mark):
            continue
        series_hit = bool(_words(ident.get("series") or ident.get("product_line")) & _words(c.series or c.product_line))
        denom_hit = _same_denomination(country, ident.get("denomination"), c.denomination)
        if not (series_hit or denom_hit):
            continue
        mint = _mint(country, c.mint_mark)
        why = " ".join(str(x) for x in (year, mint, c.series or c.product_line or c.denomination) if x)
        out.append(Match(it, why))
    return out[:6]


def same_photos(db: Session, owner_id: int, srcs: list[Source], exclude_item: int | None) -> list[tuple[Item, str]]:
    """Your items that already have one of these photos (the same file, or a near copy of it)."""
    limit = get_settings().phash_duplicate_distance
    rows = db.execute(
        select(Photo.item_id, Photo.sha256, Photo.phash).join(Item, Item.id == Photo.item_id)
        .where(Item.owner_id == owner_id, Item.deleted_at.is_(None))
    ).all()
    hits: dict[int, str] = {}
    for s in srcs:
        for item_id, sha, phash in rows:
            if item_id == exclude_item or item_id in hits:
                continue
            if sha == s.sha256:
                hits[item_id] = "exact"
            else:
                d = phash_distance(s.phash, phash)
                if d is not None and d <= limit:
                    hits[item_id] = "similar"
    if not hits:
        return []
    items = {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(hits)).options(selectinload(Item.photos)))}
    return [(items[i], k) for i, k in hits.items() if i in items][:6]
