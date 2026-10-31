import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, CompListing, CompsSearch, Item, money, NumistaIssue, NumistaType } from "../api";
import { tidy } from "./ItemForm";
import { gradeInText } from "../numistaQuery";
import NumistaSearch, { numistaQueryForItem } from "./NumistaSearch";

const WINDOWS: [string, string][] = [
  ["30", "30 days"],
  ["90", "90 days"],
  ["180", "6 months"],
  ["365", "year"],
];

const longDate = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" });

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function priceOf(l: CompListing, basis: "sold" | "total"): number | null {
  const v = basis === "total" ? l.total_price ?? l.sold_price : l.sold_price;
  return v === null ? null : Number(v);
}

/** Market value: the newest value, a way to fetch or type a new one, and the history. */
export default function MarketValue({ item }: { item: Item }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<null | "search" | "manual">(null);
  const [pcgsBusy, setPcgsBusy] = useState(false);
  const [pcgsError, setPcgsError] = useState<string | null>(null);
  const pcgsSlab = (item.condition?.grading_service ?? "").toUpperCase() === "PCGS" && Boolean(item.condition?.cert_number);
  const history = useQuery({ queryKey: ["valuations", item.id], queryFn: () => api.valuations(item.id) });
  const cur = item.values?.currency ?? "USD";

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["valuations", item.id] });
    await qc.invalidateQueries({ queryKey: ["item", item.id] });
    await qc.invalidateQueries({ queryKey: ["items"] });
    await qc.invalidateQueries({ queryKey: ["summary"] });
    await qc.invalidateQueries({ queryKey: ["providers"] });
  };

  return (
    <section className="market" aria-labelledby="market-h">
      <div className="market-head">
        <h2 id="market-h">Market value</h2>
        <div className="segmented" role="tablist" aria-label="Update market value">
          <button type="button" role="tab" aria-selected={open === "search"} className={open === "search" ? "on" : ""} onClick={() => setOpen(open === "search" ? null : "search")}>
            Search sold listings
          </button>
          <button type="button" role="tab" aria-selected={open === "manual"} className={open === "manual" ? "on" : ""} onClick={() => setOpen(open === "manual" ? null : "manual")}>
            Enter a value
          </button>
          {pcgsSlab && (
            <button
              type="button"
              disabled={pcgsBusy}
              title={`Looks up cert ${item.condition?.cert_number} and saves today's PCGS price guide value`}
              onClick={async () => {
                setPcgsBusy(true);
                setPcgsError(null);
                try {
                  await api.pcgsPriceGuide(item.id);
                  await refresh();
                } catch (err) {
                  setPcgsError((err as Error).message);
                } finally {
                  setPcgsBusy(false);
                }
              }}
            >
              {pcgsBusy ? "Asking PCGS…" : "PCGS price guide"}
            </button>
          )}
        </div>
      </div>
      {(item.item_type === "coin" || item.item_type === "bullion") && <NumistaValue item={item} onChanged={refresh} />}
      {pcgsError && <p className="error" role="alert">{pcgsError}</p>}

      {open === "search" && <CompsSearchPanel item={item} currency={cur} onSaved={async () => { await refresh(); setOpen(null); }} />}
      {open === "manual" && <ManualPanel item={item} onSaved={async () => { await refresh(); setOpen(null); }} />}

      {history.data && history.data.length > 0 ? (
        <table className="figures ledger">
          <thead>
            <tr><th>As of</th><th>Each</th><th>From</th><th aria-label="Actions" /></tr>
          </thead>
          <tbody>
            {history.data.map((v, i) => (
              <tr key={v.id} className={i === 0 ? "is-current" : ""}>
                <td>{longDate(v.as_of)}{i === 0 && <span className="hint"> (in use)</span>}</td>
                <td className="tabular">{money(v.value_each, v.currency)}</td>
                <td>
                  {v.source ?? (v.kind === "comps" ? "Sold listings" : "Entered by you")}
                  {v.details?.keyword && <span className="hint"> for “{v.details.keyword}”, {v.details.basis === "total" ? "with" : "without"} shipping</span>}
                  {v.notes && <span className="hint"> {v.notes}</span>}
                </td>
                <td>
                  <button
                    className="ghost small danger"
                    onClick={async () => {
                      if (!window.confirm(`Delete the ${money(v.value_each, v.currency)} value from ${longDate(v.as_of)}?`)) return;
                      await api.deleteValuation(v.id);
                      await refresh();
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        !open && <p className="muted">No market value yet. Search recent eBay sales, or enter a dealer quote or price-guide figure.</p>
      )}
    </section>
  );
}

function ManualPanel({ item, onSaved }: { item: Item; onSaved: () => Promise<void> }) {
  const today = new Date().toISOString().slice(0, 10);
  const [value, setValue] = useState("");
  const [asOf, setAsOf] = useState(today);
  const [source, setSource] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="market-panel"
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api.addValuation(item.id, { kind: "manual", value_each: value.trim(), as_of: asOf, source: source.trim() || null, notes: notes.trim() || null });
          await onSaved();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="grid2">
        <label>
          Value of one piece
          <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="85.00" required />
          {item.quantity > 1 && <span className="hint">For all {item.quantity}: {value && Number(value) ? money(String(Number(value) * item.quantity), item.values?.currency) : "—"}</span>}
        </label>
        <label>
          As of
          <input type="date" value={asOf} max={today} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <label>
          Source
          <input list="value-sources" value={source} onChange={(e) => setSource(e.target.value)} placeholder="Dealer quote" />
          <datalist id="value-sources">
            <option value="Dealer quote" /><option value="PCGS Price Guide" /><option value="NGC Price Guide" />
            <option value="Greysheet" /><option value="Appraisal" /><option value="Auction result" />
          </datalist>
        </label>
        <label>
          Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional" />
        </label>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions inline">
        <button className="primary" disabled={busy || !value.trim()}>{busy ? "Saving…" : "Save market value"}</button>
      </div>
    </form>
  );
}

function CompsSearchPanel({ item, currency, onSaved }: { item: Item; currency: string; onSaved: () => Promise<void> }) {
  const suggested = useQuery({ queryKey: ["comps-keyword", item.id], queryFn: () => api.compsKeyword(item.id), staleTime: Infinity });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const soldcomps = providers.data?.find((p) => p.key === "soldcomps");
  const [keyword, setKeyword] = useState("");
  const [days, setDays] = useState("90");
  const [condition, setCondition] = useState("any");
  const [exact, setExact] = useState(true);
  const [result, setResult] = useState<CompsSearch | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [basis, setBasis] = useState<"sold" | "total">("sold");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (suggested.data && !keyword) setKeyword(suggested.data.keyword);
  }, [suggested.data, keyword]);

  const chosen = useMemo(() => (result?.listings ?? []).filter((l) => picked.has(l.item_id)), [result, picked]);
  const prices = chosen.map((l) => priceOf(l, basis)).filter((x): x is number => x !== null);
  const med = median(prices);

  if (soldcomps && !soldcomps.key_set) {
    return (
      <div className="market-panel">
        <p>Searching sold listings uses your SoldComps key. Add it under <Link to="/settings#providers">Settings, Data providers</Link>, then come back here.</p>
      </div>
    );
  }
  const usage = soldcomps?.usage;
  const limits = usage ? [usage.cap, usage.provider_limit].filter((x): x is number => x !== null) : [];
  const usageText = usage ? ` (${usage.used}${limits.length ? ` of ${Math.min(...limits)}` : ""} used this period)` : "";

  const search = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.searchComps(item.id, { keyword: keyword.trim(), sold_within_days: days ? Number(days) : null, condition, exact_match: exact });
      setResult(r);
      setPicked(new Set(r.listings.filter((l) => l.sold_price).map((l) => l.item_id)));
      await providers.refetch();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.addValuation(item.id, { kind: "comps", comps: { keyword: result!.keyword, basis, listings: chosen } });
      await onSaved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="market-panel">
      <form className="comps-form" onSubmit={search}>
        <label className="comps-keyword">
          Search eBay sold listings for
          <input value={keyword} onChange={(e) => setKeyword(e.target.value)} required minLength={2} />
        </label>
        <label>
          Sold in the last
          <select value={days} onChange={(e) => setDays(e.target.value)}>
            {WINDOWS.map(([d, l]) => <option key={d} value={d}>{l}</option>)}
          </select>
        </label>
        <label>
          Condition
          <select value={condition} onChange={(e) => setCondition(e.target.value)}>
            <option value="any">Any</option>
            <option value="used">Used</option>
            <option value="new">New</option>
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={exact} onChange={(e) => setExact(e.target.checked)} />
          Exact words only
        </label>
        <button className="primary" disabled={busy || keyword.trim().length < 2}>{busy && !result ? "Searching…" : "Search"}</button>
        <p className="hint comps-cost">Each search uses one SoldComps request{usageText}.</p>
      </form>
      {error && <p className="error" role="alert">{error}</p>}

      {result && (
        <>
          <div className="comps-summary" role="status">
            <div>
              <span className="kpi-label">Median of {prices.length} picked</span>
              <span className="value-big">{med !== null ? money(String(med), currency) : "—"}</span>
              <span className="hint">
                each{item.quantity > 1 && med !== null ? `, ${money(String(med * item.quantity), currency)} for all ${item.quantity}` : ""}
              </span>
            </div>
            <div className="comps-actions">
              <div className="segmented" role="radiogroup" aria-label="Price to use">
                <button type="button" role="radio" aria-checked={basis === "sold"} className={basis === "sold" ? "on" : ""} onClick={() => setBasis("sold")}>Price</button>
                <button type="button" role="radio" aria-checked={basis === "total"} className={basis === "total" ? "on" : ""} onClick={() => setBasis("total")}>Price + shipping</button>
              </div>
              <button className="primary" disabled={busy || prices.length === 0} onClick={save}>Save as market value</button>
            </div>
          </div>
          <p className="hint">
            {result.listings.length} sold {result.listings.length === 1 ? "listing" : "listings"}
            {result.total_results ? ` shown of about ${result.total_results} on eBay` : ""}. Untick any that aren't the same coin, grade or variety.
            {result.other_currency > 0 && ` ${result.other_currency} sold in another currency and ${result.other_currency === 1 ? "is" : "are"} left out.`}
          </p>
          {result.listings.length === 0 ? (
            <p className="muted">No sold listings matched. Try fewer words, untick “Exact words only”, or a longer time range.</p>
          ) : (
            <ul className="comps">
              {result.listings.map((l) => {
                const on = picked.has(l.item_id);
                const p = priceOf(l, basis);
                return (
                  <li key={l.item_id} className={on ? "" : "is-off"}>
                    <label className="comp-pick">
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={p === null}
                        onChange={(e) =>
                          setPicked((s) => {
                            const n = new Set(s);
                            if (e.target.checked) n.add(l.item_id);
                            else n.delete(l.item_id);
                            return n;
                          })
                        }
                      />
                      <span className="visually-hidden">Use {l.title}</span>
                    </label>
                    {l.thumbnail_url ? <img src={l.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="comp-noimg" />}
                    <span className="comp-title">
                      <a href={l.url} target="_blank" rel="noreferrer">{l.title ?? "Untitled listing"}</a>
                      <span className="hint">
                        {[l.ended_at ? `Sold ${longDate(l.ended_at)}` : null, l.condition, l.buying_format === "auction" ? "auction" : l.best_offer ? "best offer" : null]
                          .filter(Boolean)
                          .join(", ")}
                      </span>
                    </span>
                    <span className="comp-price tabular">
                      {l.sold_price ? money(l.sold_price, currency) : "—"}
                      <span className="hint">{l.shipping_price ? `+ ${money(l.shipping_price, currency)} ship` : "free ship"}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/** Link the item to its Numista coin (search from its own details) and save Numista's estimate for its grade. */
function NumistaValue({ item, onChanged }: { item: Item; onChanged: () => Promise<void> }) {
  const det = item.details as Record<string, unknown>;
  const numistaId = typeof det.numista_id === "number" ? det.numista_id : null;
  const issueId = typeof det.numista_issue_id === "number" ? det.numista_issue_id : null;
  const filledGrade = item.condition?.grade_text || (item.condition?.sheldon_grade ? String(item.condition.sheldon_grade) : "");
  const titleGrade = filledGrade ? null : gradeInText(`${item.title} ${String(det.variety_notes ?? "")}`);
  const graded = Boolean(filledGrade || titleGrade);
  const [mode, setMode] = useState<null | "find" | "issue">(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const estimate = async () => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const v = await api.numistaEstimate(item.id);
      await onChanged();
      setNote(`Saved Numista's estimate: ${money(v.value_each, v.currency)} each.`);
    } catch (err) {
      const msg = (err as Error).message;
      setError(msg);
      if (/Pick which issue/i.test(msg)) setMode("issue");
    } finally {
      setBusy(false);
    }
  };

  /** Save the Numista coin and issue on the item, filling only details that are blank, then price it if graded. */
  const link = async (t: NumistaType, issue: NumistaIssue | null) => {
    const blank = (k: string) => det[k] === null || det[k] === undefined || det[k] === "";
    const details: Record<string, unknown> = { numista_id: t.id, numista_issue_id: issue?.id ?? null };
    for (const [k, v] of Object.entries(t.details)) if (k !== "numista_id" && blank(k)) details[k] = v;
    const y = issue?.year ?? issue?.gregorian_year;
    if (y && blank("year")) details.year = y;
    if (issue?.mint_letter && blank("mint_mark")) details.mint_mark = issue.mint_letter;
    const body: Record<string, unknown> = { details };
    if (t.metal && item.metal_content.length === 0) {
      body.metal_content = [{ metal: t.metal.metal, gross_weight_g: tidy(t.metal.gross_weight_g), fineness: tidy(t.metal.fineness) }];
    }
    await api.updateItem(item.id, item.version, body);
    await onChanged();
    setMode(null);
    setNote(`Linked to Numista N# ${t.id}${y ? ` (${y}${issue?.mint_letter ? ` ${issue.mint_letter}` : ""})` : ""}.`);
    if (graded && issue) await estimate();
  };

  const action = graded ? "Link and get estimate" : "Link this coin";
  return (
    <div className="market-numista">
      <div className="market-numista-row">
        {numistaId ? (
          <>
            <button type="button" className="ghost small" disabled={busy || !graded} title={graded ? "Saves Numista's estimate for this coin's year, mint and grade" : "Add the grade first"} onClick={estimate}>
              {busy ? "Asking Numista…" : "Get Numista's estimate"}
            </button>
            <button type="button" className="ghost small" onClick={() => setMode(mode === "issue" ? null : "issue")}>
              {issueId ? "Change year" : "Pick the year"}
            </button>
            <button type="button" className="ghost small" onClick={() => setMode(mode === "find" ? null : "find")}>Link a different coin</button>
            <span className="hint">
              Numista N# {numistaId}
              {!graded ? ". Add a grade to get an estimate." : titleGrade ? `. Using ${titleGrade} from the title; fill in the grade to change it.` : ""}
            </span>
          </>
        ) : (
          <>
            <button type="button" className="ghost small" onClick={() => setMode(mode === "find" ? null : "find")}>Find on Numista</button>
            <span className="hint">Links this coin to Numista for its price estimate{graded ? "" : " (add a grade to get one)"}.</span>
          </>
        )}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {note && <p className="success">{note}</p>}
      {mode === "find" && (
        <NumistaSearch start={numistaQueryForItem(item)} hint={hintFor(item)} actionLabel={action} doneLabel="Linked." onPick={link} onCancel={() => setMode(null)} />
      )}
      {mode === "issue" && numistaId && (
        <NumistaSearch
          start={numistaQueryForItem(item)}
          hint={hintFor(item)}
          typeId={numistaId}
          issueId={issueId}
          actionLabel={action}
          doneLabel="Saved."
          onPick={link}
          onCancel={() => setMode(null)}
        />
      )}
    </div>
  );
}

/** The words that tell versions apart: the title, grade and designations ("PR70 DCAM", "SP69", "T2"). */
function hintFor(item: Item): string {
  const c = item.condition;
  return [item.title, c?.grade_text, ...(c?.designations ?? []), String((item.details as Record<string, unknown>).variety_notes ?? "")].filter(Boolean).join(" ");
}
