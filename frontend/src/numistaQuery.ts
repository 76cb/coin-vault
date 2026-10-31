/** Turning a coin's details or a listing title into a Numista search. No imports, so it can be tested alone. */

export interface NumistaStart {
  q: string;
  year: string;
  mark?: string;
}

// US denomination codes as Numista words them in titles ("Morgan" + "$1" -> "Morgan Dollar")
const US_DENOM_WORDS: Record<string, string> = {
  "1c": "Cent", "3c": "3 Cents", "5c": "5 Cents", "10c": "Dime", "20c": "20 Cents", "25c": "Quarter", "50c": "Half Dollar",
  "$1": "Dollar", "$2.50": "Quarter Eagle", "$3": "3 Dollars", "$5": "Half Eagle", "$10": "Eagle", "$20": "Double Eagle",
};

// listing words Numista titles never contain: graders, grades, designations, holder labels, types
const NOISE = [
  /\b(PCGS|NGC|ANACS|ICG|CACG|SEGS|CAC|OGH)\b/gi,
  /\b(MS|PR|PF|SP|AU|XF|EF|VF|VG|AG|FR|PO)[\s-]?\d{1,2}\+?(?=\W|$)/gi,
  /\b(first|early|advanced?)\s+(day\s+of\s+issue|production|strike|releases?)\b/gi,
  /\blast\s+day\s+of\s+production\b/gi,
  /\b(ultra|deep)\s+cameo\b|\b(UCAM|DCAM|DMPL|PL|FDOI|FDI|FBL|FB|FS|FH)\b|\bcameo\b|\bproof[\s-]?like\b/gi,
  /\bT-?[12]\b|\btype\s+[12]\b/gi,
  /\b(BU|UNC|GEM|CHOICE|NICE|RARE|KEY\s+DATE|LOT|COIN|COINS|SLAB|HOLDER|GRADED|CERTIFIED)\b/gi,
  /\b\d{6,}-\d{3}\b|\b\d{6,}\b/g, // cert numbers (NGC writes 1234567-001)
  /\bcert(ificate)?\b\s*#?|\bno\.?\s*#?(?=\s|$)/gi,
];
// a holder label and everything after it (signers' names follow it)
const LABEL_TAIL = /\b(legends?\s+(of\s+)?life|flag\s+label|eagle\s+label|blue\s+label|gold\s+foil|hand[\s-]?signed|signed|signature|autographed?)\b.*$/i;

/** A listing title cut down to words Numista could match. */
export function cleanTitle(title: string): string {
  let t = title.replace(LABEL_TAIL, " ");
  for (const re of NOISE) t = t.replace(re, " ");
  return t.replace(/[|,;:()[\]]+/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * What to search Numista for, from the details we have: the coin's name (series or product) with its denomination,
 * plus the country unless it's the US; else the country and denomination; else the cleaned title.
 */
export function buildNumistaQuery(det: Record<string, unknown>, title: string): NumistaStart {
  const str = (k: string) => (typeof det[k] === "string" && det[k] ? String(det[k]).trim() : "");
  const country = str("country");
  const foreign = country && country !== "United States" ? country : "";
  const name = str("product_line") || str("series");
  const rawDenom = str("denomination");
  const denom = US_DENOM_WORDS[rawDenom] ?? (/^\$|^\d+c$/.test(rawDenom) ? "" : rawDenom);
  let words: string[] = [];
  if (name) {
    words = [foreign, name];
    // add the denomination unless the name already says it ("Morgan" + "Dollar"; not "American Silver Eagle" + "Dollar")
    if (denom && !name.toLowerCase().includes(denom.toLowerCase()) && !str("product_line")) words.push(denom);
  } else if (foreign && denom) {
    words = [foreign, denom];
  }
  const q = words.filter(Boolean).join(" ") || cleanTitle(title).replace(/\b(1[5-9]|20)\d\d(-[A-Z]{1,2})?\b/g, " ").replace(/\s+/g, " ").trim();
  const year = det.year ? String(det.year) : (title.match(/\b(1[5-9]\d\d|20\d\d)\b/)?.[1] ?? "");
  return { q: q.slice(0, 120), year, mark: str("mint_mark") || undefined };
}


// --- Choosing the right Numista coin and issue -------------------------------------------------

export interface Wants {
  proof: boolean | null; // true: PR/PF or "proof"; false: MS, BU or Unc; null: not said
  burnished: boolean; // "Burnished", or an SP grade
  reverseProof: boolean;
  type2: boolean; // "T2", "Type 2"
  mark: string; // mint mark, upper case, or ""
}

/** What the owner's title, grade and details say about which version of a coin this is. */
export function wantsFrom(text: string, mark?: string | null): Wants {
  const reverseProof = /reverse\s*proof|\bRP\b/i.test(text);
  const proofSaid = /\b(PR|PF)[\s-]?\d{1,2}\b|\bproof\b/i.test(text.replace(/reverse\s*proof/gi, "")) || reverseProof;
  const msSaid = /\bMS[\s-]?\d{1,2}\b|\bBU\b|\bunc(irculated)?\b/i.test(text);
  return {
    proof: proofSaid ? true : msSaid ? false : null,
    burnished: /\bburnished\b|\bSP[\s-]?\d{1,2}\b/i.test(text),
    reverseProof,
    type2: /\bT-?2\b|\btype\s*(2|ii)\b/i.test(text),
    mark: (mark ?? "").trim().toUpperCase(),
  };
}

interface IssueLike { year: number | null; gregorian_year: number | null; mint_letter: string | null; comment: string | null }

/** How well an issue fits: mint mark first, then proof, burnished or reverse proof as the owner described it. */
export function scoreIssue(i: IssueLike, w: Wants): number {
  const letter = (i.mint_letter ?? "").toUpperCase();
  const c = (i.comment ?? "").toLowerCase();
  const isReverse = c.includes("reverse proof");
  const isProof = !isReverse && /\bproof\b/.test(c);
  const isBurnished = c.includes("burnished");
  let s = 0;
  if (w.mark) s += letter === w.mark ? 4 : letter ? -4 : -1;
  else s += letter ? -1 : 2;
  if (isReverse) s += w.reverseProof ? 5 : -5;
  if (isProof) s += w.proof === true && !w.reverseProof ? 3 : w.proof === false ? -3 : -1;
  if (isBurnished) s += w.burnished ? 3 : -2;
  if (!isProof && !isReverse && !isBurnished && (w.proof === true || w.burnished)) s -= 2;
  return s;
}

const issueYear = (i: IssueLike) => i.year ?? i.gregorian_year;

/** The issues of one year, best fit first; and the best one's index when it clearly beats the rest. */
export function rankIssues<T extends IssueLike>(issues: T[], year: number | null, w: Wants): { ranked: T[]; best: T | null } {
  const pool = year ? issues.filter((i) => issueYear(i) === year) : issues;
  const scored = pool.map((i) => ({ i, s: scoreIssue(i, w) })).sort((a, b) => b.s - a.s);
  const best = scored.length === 1 || (scored.length > 1 && scored[0].s > scored[1].s) ? scored[0].i : null;
  return { ranked: scored.map((x) => x.i), best };
}

interface HitLike { title: string | null; min_year: number | null; max_year: number | null }

/** Search results with the likeliest coin first: years that include the coin's, Type 2 or proof as described. */
export function rankHits<T extends HitLike>(hits: T[], year: number | null, w: Wants): T[] {
  const score = (h: T) => {
    const t = (h.title ?? "").toLowerCase();
    let s = 0;
    if (year && h.min_year && h.max_year) s += year >= h.min_year && year <= h.max_year ? 3 : -3;
    const saysType2 = /type\s*(2|ii)\b/.test(t);
    if (w.type2) s += saysType2 ? 3 : /type\s*(1|i)\b/.test(t) ? -2 : 0;
    else if (saysType2 && year && year < 2021) s -= 1;
    if (/\bproof\b/.test(t)) s += w.proof === true ? 2 : w.proof === false ? -2 : 0;
    return s;
  };
  return hits.map((h, n) => ({ h, n, s: score(h) })).sort((a, b) => b.s - a.s || a.n - b.n).map((x) => x.h);
}
