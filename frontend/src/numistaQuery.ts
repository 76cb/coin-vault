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

