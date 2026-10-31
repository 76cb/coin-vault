import { FormEvent, useEffect, useRef, useState } from "react";

import { api, Described, Item, NumistaHit, NumistaIssue, NumistaType } from "../api";
import { buildNumistaQuery, NumistaStart, rankHits, rankIssues, wantsFrom } from "../numistaQuery";

export type { NumistaStart };

const years = (h: { min_year: number | null; max_year: number | null }) =>
  h.min_year && h.max_year && h.min_year !== h.max_year ? `${h.min_year}–${h.max_year}` : String(h.min_year ?? h.max_year ?? "");

/** What to search Numista for, from the title reader's result (or the text itself). */
export function numistaQuery(text: string, d: Described | null): NumistaStart {
  return buildNumistaQuery((d?.details ?? {}) as Record<string, unknown>, text);
}

/** The same, from a saved item's details. */
export function numistaQueryForItem(item: Item): NumistaStart {
  return buildNumistaQuery(item.details as Record<string, unknown>, item.title);
}

function issueLabel(i: NumistaIssue): string {
  const year = i.year ?? i.gregorian_year ?? "Undated";
  const parts = [`${year}${i.mint_letter ? ` ${i.mint_letter}` : ""}`];
  if (i.comment) parts.push(i.comment);
  if (i.mintage) parts.push(`${i.mintage.toLocaleString()} struck`);
  return parts.join(", ");
}

/**
 * Search the Numista catalogue, pick a coin and its issue, and hand them to onPick. Each search or newly opened
 * coin uses Numista requests (repeats come from the app's cache).
 */
export default function NumistaSearch({
  start,
  hint = "",
  typeId,
  issueId: savedIssue,
  actionLabel,
  doneLabel,
  onPick,
  onCancel,
}: {
  start: NumistaStart;
  hint?: string; // the owner's title and grade: says proof, burnished, Type 2 and so on
  typeId?: number | null; // open this coin straight away (to pick or change its issue)
  issueId?: number | null;
  actionLabel: string;
  doneLabel: string;
  onPick: (t: NumistaType, issue: NumistaIssue | null) => Promise<void> | void;
  onCancel?: () => void;
}) {
  const [q, setQ] = useState(start.q);
  const [year, setYear] = useState(start.year);
  const [hits, setHits] = useState<NumistaHit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [chosen, setChosen] = useState<NumistaType | null>(null);
  const [issueId, setIssueId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const [widened, setWidened] = useState<string | null>(null);
  const [allIssues, setAllIssues] = useState(false);
  const edited = useRef(false);
  const wants = wantsFrom(`${hint} ${start.q}`, start.mark);
  const yearNum = /^\d{3,4}$/.test(year.trim()) ? Number(year.trim()) : /^\d{3,4}$/.test(start.year) ? Number(start.year) : null;

  // the title reader may answer after this opens: take its words unless the owner typed here
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

  const open = async (id: number) => {
    const t = await run(() => api.numistaType(id));
    if (!t) return;
    setChosen(t);
    setApplied(false);
    const saved = savedIssue && t.issues.some((i) => i.id === savedIssue) ? String(savedIssue) : "";
    const { ranked, best } = rankIssues(t.issues, yearNum, wants);
    setAllIssues(ranked.length === 0);
    setIssueId(saved || (best ? String(best.id) : t.issues.length === 1 ? String(t.issues[0].id) : ""));
  };

  useEffect(() => {
    if (typeId) open(typeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeId]);

  const search = async (e?: FormEvent) => {
    e?.preventDefault();
    const y = /^\d{1,4}(-\d{1,4})?$/.test(year.trim()) ? year.trim() : undefined;
    let r = await run(() => api.numistaSearch(q.trim(), y));
    // nothing in that year: Numista's years can differ from the seller's, so try once without it
    if (r && r.count === 0 && y) {
      const all = await run(() => api.numistaSearch(q.trim()));
      if (all && all.count > 0) {
        r = all;
        setYear("");
        setError(null);
        setWidened(`Nothing listed for ${y}; showing every year.`);
      }
    } else {
      setWidened(null);
    }
    if (r) {
      setHits(rankHits(r.types, yearNum, wants));
      setTotal(r.count);
      setChosen(null);
    }
  };

  const pick = async () => {
    if (!chosen) return;
    const issue = chosen.issues.find((i) => String(i.id) === issueId) ?? null;
    const ok = await run(async () => { await onPick(chosen, issue); return true; });
    if (ok) setApplied(true);
  };

  return (
    <div className="numista">
      {!(typeId && chosen) && (
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
      )}
      {error && <p className="error" role="alert">{error}</p>}

      {hits && !chosen && (
        hits.length ? (
          <>
            {widened && <p className="hint">{widened}</p>}
            <p className="hint">{total > hits.length ? `${hits.length} of ${total.toLocaleString()} matches; add a year or more words to narrow it.` : `${hits.length} ${hits.length === 1 ? "match" : "matches"}.`}</p>
            <ul className="numista-hits">
              {hits.map((h) => (
                <li key={h.id}>
                  <button type="button" disabled={busy} onClick={() => open(h.id)}>
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

      {busy && typeId && !chosen && <p className="hint">Opening the coin on Numista…</p>}

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
          {chosen.issues.length > 0 && <IssuePicker type={chosen} year={yearNum} wants={wants} value={issueId} all={allIssues} onAll={setAllIssues} onChange={(v) => { setIssueId(v); setApplied(false); }} />}
          <div className="numista-actions">
            {typeId ? (
              onCancel && <button type="button" className="ghost small" onClick={onCancel}>Close</button>
            ) : (
              <button type="button" className="ghost small" onClick={() => setChosen(null)}>Back to results</button>
            )}
            {applied ? (
              <p className="success qs-applied">{doneLabel}</p>
            ) : (
              <button type="button" className="primary" disabled={busy} onClick={pick}>{busy ? "Working…" : actionLabel}</button>
            )}
          </div>
        </div>
      )}
      {!chosen && onCancel && (
        <button type="button" className="ghost small numista-close" onClick={onCancel}>Close</button>
      )}
    </div>
  );
}

/** The issues of the coin's year as a short list, best fit first and marked; every year on request. */
function IssuePicker({ type, year, wants, value, all, onAll, onChange }: {
  type: NumistaType; year: number | null; wants: ReturnType<typeof wantsFrom>; value: string; all: boolean;
  onAll: (v: boolean) => void; onChange: (v: string) => void;
}) {
  const { ranked, best } = rankIssues(type.issues, year, wants);
  const shown = all || ranked.length === 0
    ? [...type.issues].sort((a, b) => (b.year ?? b.gregorian_year ?? 0) - (a.year ?? a.gregorian_year ?? 0))
    : ranked;
  return (
    <fieldset className="issue-pick">
      <legend>
        Which issue
        <span className="hint">
          {" "}{all || ranked.length === 0 ? `all ${type.issues.length}` : `${ranked.length} for ${year}`}
          {wants.proof === true ? ", you said proof" : wants.proof === false ? ", you said MS (not proof)" : ""}
          {wants.burnished ? ", burnished" : ""}{wants.mark ? `, mint mark ${wants.mark}` : ""}
        </span>
      </legend>
      <ul className="issue-list" role="radiogroup" aria-label="Which issue">
        {shown.map((i) => (
          <li key={i.id}>
            <button type="button" role="radio" aria-checked={String(i.id) === value} className={String(i.id) === value ? "is-selected" : ""} onClick={() => onChange(String(i.id))}>
              <span>{issueLabel(i)}</span>
              {best && best.id === i.id && !all && <span className="issue-best">Best match</span>}
            </button>
          </li>
        ))}
      </ul>
      <div className="issue-more">
        {ranked.length > 0 && (
          <button type="button" className="ghost small" onClick={() => onAll(!all)}>
            {all ? `Only ${year}` : `Show every year (${type.issues.length})`}
          </button>
        )}
        {value && <button type="button" className="ghost small" onClick={() => onChange("")}>Not sure</button>}
      </div>
      <span className="hint">The issue sets the year and mint mark, and Numista prices each issue separately.</span>
    </fieldset>
  );
}
