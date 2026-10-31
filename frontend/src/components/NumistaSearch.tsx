import { FormEvent, useEffect, useRef, useState } from "react";

import { api, Described, NumistaHit, NumistaIssue, NumistaType } from "../api";
import { defaultsFromDescription, defaultsFromNumista, FormState } from "./ItemForm";

const years = (h: { min_year: number | null; max_year: number | null }) =>
  h.min_year && h.max_year && h.min_year !== h.max_year ? `${h.min_year}–${h.max_year}` : String(h.min_year ?? h.max_year ?? "");

/** What to search Numista for: the country, denomination and series the title reader found, else the text itself. */
export function numistaQuery(text: string, d: Described | null): { q: string; year: string } {
  const det = d?.details ?? {};
  const words = [det.country === "United States" ? "" : det.country, det.product_line ?? det.series, det.denomination]
    .filter((x) => typeof x === "string" && x && !/^\$|^\d+c$/.test(x)) as string[];
  const q = words.length >= 2 ? words.join(" ") : text.replace(/\b(PCGS|NGC|ANACS|ICG|MS|PR|PF|AU|XF|VF)\s?-?\d{0,2}\b/gi, "").replace(/\s+/g, " ").trim();
  return { q: q.slice(0, 120), year: det.year ? String(det.year) : "" };
}

function issueLabel(i: NumistaIssue): string {
  const year = i.year ?? i.gregorian_year ?? "Undated";
  const parts = [`${year}${i.mint_letter ? ` ${i.mint_letter}` : ""}`];
  if (i.comment) parts.push(i.comment);
  if (i.mintage) parts.push(`${i.mintage.toLocaleString()} struck`);
  return parts.join(", ");
}

/** Search the Numista catalogue and fill the form from a coin. Each search or new coin uses Numista requests. */
export default function NumistaSearch({ text, described, onUse }: { text: string; described: Described | null; onUse: (d: Partial<FormState>) => void }) {
  const start = numistaQuery(text, described);
  const [q, setQ] = useState(start.q);
  const [year, setYear] = useState(start.year);
  const [hits, setHits] = useState<NumistaHit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [chosen, setChosen] = useState<NumistaType | null>(null);
  const [issueId, setIssueId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const edited = useRef(false);

  // the title reader may answer after this opens: take its country and denomination unless the owner typed here
  useEffect(() => {
    if (edited.current) return;
    setQ(start.q);
    setYear(start.year);
  }, [start.q, start.year]);

  const run = async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError((err as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const search = async (e?: FormEvent) => {
    e?.preventDefault();
    const r = await run(() => api.numistaSearch(q.trim(), /^\d{1,4}(-\d{1,4})?$/.test(year.trim()) ? year.trim() : undefined));
    if (r) {
      setHits(r.types);
      setTotal(r.count);
      setChosen(null);
    }
  };

  const choose = async (h: NumistaHit) => {
    const t = await run(() => api.numistaType(h.id));
    if (!t) return;
    setChosen(t);
    setApplied(false);
    // preselect the issue matching the year (and mint mark) from the title, if exactly one does
    const y = Number(year || described?.details.year);
    const mark = String(described?.details.mint_mark ?? "").toUpperCase();
    let match = t.issues.filter((i) => (i.year ?? i.gregorian_year) === y);
    if (mark) match = match.filter((i) => (i.mint_letter ?? "").toUpperCase() === mark).length ? match.filter((i) => (i.mint_letter ?? "").toUpperCase() === mark) : match;
    setIssueId(match.length === 1 ? String(match[0].id) : t.issues.length === 1 ? String(t.issues[0].id) : "");
  };

  const fill = () => {
    if (!chosen) return;
    const issue = chosen.issues.find((i) => String(i.id) === issueId) ?? null;
    const base = described ? defaultsFromDescription(described) : { title: text.trim() };
    onUse(defaultsFromNumista(chosen, issue, base));
    setApplied(true);
  };

  return (
    <div className="numista">
      <form className="numista-search" onSubmit={search}>
        <label>
          Search Numista
          <input value={q} onChange={(e) => { edited.current = true; setQ(e.target.value); }} placeholder="Poland 5 złotych" />
        </label>
        <label className="numista-year">
          Year
          <input value={year} onChange={(e) => { edited.current = true; setYear(e.target.value); }} inputMode="numeric" placeholder="1934" />
        </label>
        <button type="submit" disabled={busy || q.trim().length < 2}>{busy && !chosen ? "Searching…" : "Search"}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}

      {hits && !chosen && (
        hits.length ? (
          <>
            <p className="hint">{total > hits.length ? `${hits.length} of ${total.toLocaleString()} matches; add a year or more words to narrow it.` : `${hits.length} ${hits.length === 1 ? "match" : "matches"}.`}</p>
            <ul className="numista-hits">
              {hits.map((h) => (
                <li key={h.id}>
                  <button type="button" disabled={busy} onClick={() => choose(h)}>
                    {h.obverse_thumbnail ? <img src={h.obverse_thumbnail} alt="" referrerPolicy="no-referrer" loading="lazy" /> : <span className="numista-noimg" />}
                    <span className="numista-hit-text">
                      <strong>{h.title}</strong>
                      <span className="hint">{[h.issuer, years(h), `N# ${h.id}`].filter(Boolean).join(", ")}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="hint">Numista found nothing for that. Try fewer words, the country and denomination, or no year.</p>
        )
      )}

      {chosen && (
        <div className="numista-chosen">
          <div className="numista-coin">
            {chosen.obverse_thumb && <img src={chosen.obverse_thumb} alt="" referrerPolicy="no-referrer" />}
            {chosen.reverse_thumb && <img src={chosen.reverse_thumb} alt="" referrerPolicy="no-referrer" />}
            <div>
              <p><strong>{chosen.title}</strong></p>
              <p className="hint">{[chosen.issuer, years(chosen), chosen.references.slice(0, 2).join(", ")].filter(Boolean).join(", ")}</p>
              <p>
                {chosen.composition ?? "Composition not given"}
                {chosen.weight_g ? `, ${Number(chosen.weight_g)} g` : ""}
              </p>
              {!chosen.metal && <p className="hint">No precious-metal fineness on Numista for this coin; the metal fields stay as they are.</p>}
              {chosen.url && <p><a href={chosen.url} target="_blank" rel="noreferrer">Numista page</a></p>}
            </div>
          </div>
          {chosen.issues.length > 0 && (
            <label>
              Which issue
              <select value={issueId} onChange={(e) => setIssueId(e.target.value)}>
                <option value="">Not sure yet</option>
                {chosen.issues.map((i) => <option key={i.id} value={i.id}>{issueLabel(i)}</option>)}
              </select>
              <span className="hint">The issue sets the year and mint mark, and lets you get Numista's price estimate later.</span>
            </label>
          )}
          <div className="numista-actions">
            <button type="button" className="ghost small" onClick={() => setChosen(null)}>Back to results</button>
            {applied ? (
              <p className="success qs-applied">Filled in below.</p>
            ) : (
              <button type="button" className="primary" onClick={fill}>Fill in from Numista</button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
