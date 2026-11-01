import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, GoldbackCatalogue, money } from "../api";

const oz = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 4 });
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

/** Goldbacks: how many you hold by series and denomination, and adding more by picking them. */
export default function Goldbacks() {
  const summary = useQuery({ queryKey: ["goldbacks", "summary"], queryFn: api.goldbackSummary });
  const catalogue = useQuery({ queryKey: ["goldbacks", "catalogue"], queryFn: api.goldbackCatalogue, staleTime: Infinity });
  const s = summary.data;

  return (
    <>
      <div className="page-head">
        <h1>Goldbacks</h1>
        <div className="head-actions">
          <Link className="button ghost" to="/?type=goldback">See them in the collection</Link>
        </div>
      </div>
      <p className="muted lede">
        Each Goldback holds 1/1000 troy ounce of 24-karat gold, so a 5 holds 0.005 oz. Their melt value follows the gold price.
      </p>

      <section className="panel gb-summary" aria-labelledby="gb-have">
        <h2 id="gb-have">What you have</h2>
        {summary.isPending && <p className="muted">Loading…</p>}
        {s && s.rows.length === 0 && <p className="muted">No Goldbacks yet. Add the ones you have below.</p>}
        {s && s.rows.length > 0 && (
          <>
            <p className="gb-totals">
              <strong className="tabular">{plural(s.notes, "note")}</strong>
              <span className="tabular">{Number(s.goldbacks).toLocaleString()} Goldbacks</span>
              <span className="tabular">{oz(Number(s.gold_toz))} oz gold</span>
              {s.melt && <span className="tabular">{money(s.melt, s.currency)} at spot</span>}
            </p>
            <table className="figures gb-table">
              <thead>
                <tr><th>State or series</th><th>Denomination</th><th>Notes</th><th className="gb-wide">Goldbacks</th><th>Gold</th><th>Melt</th></tr>
              </thead>
              <tbody>
                {s.rows.map((r) => (
                  <tr key={`${r.state}-${r.label}`}>
                    <td>
                      {r.item_ids.length === 1 ? <Link to={`/items/${r.item_ids[0]}`}>{r.state ?? "Not set"}</Link> : (
                        <Link to={`/?type=goldback&q=${encodeURIComponent(r.state ?? "")}`}>{r.state ?? "Not set"}</Link>
                      )}
                    </td>
                    <td className="tabular">{r.label}</td>
                    <td className="tabular">{r.notes.toLocaleString()}</td>
                    <td className="tabular gb-wide">{Number(r.goldbacks).toLocaleString()}</td>
                    <td className="tabular">{oz(Number(r.gold_toz))} oz</td>
                    <td className="tabular">{r.melt ? money(r.melt, s.currency) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {catalogue.data && <AddGoldbacks catalogue={catalogue.data} />}
    </>
  );
}

function AddGoldbacks({ catalogue }: { catalogue: GoldbackCatalogue }) {
  const qc = useQueryClient();
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const [state, setState] = useState<string>("");
  const [other, setOther] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [paid, setPaid] = useState<Record<string, string>>({});
  const [rare, setRare] = useState(false);
  const [year, setYear] = useState("");
  const [variety, setVariety] = useState("");
  const [acquired, setAcquired] = useState("");
  const [location, setLocation] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ ids: number[]; text: string } | null>(null);

  const first = catalogue.series.find((x) => x.name === state)?.first_year ?? 2019;
  const thisYear = new Date().getFullYear();
  const years = Array.from({ length: Math.max(1, thisYear + 1 - first + 1) }, (_, i) => first + i);
  const shown = catalogue.denominations.filter((d) => d.common || rare || (counts[d.value] ?? 0) > 0);
  const chosen = catalogue.denominations.filter((d) => (counts[d.value] ?? 0) > 0);
  const totals = useMemo(() => chosen.reduce(
    (t, d) => ({ notes: t.notes + counts[d.value], goldbacks: t.goldbacks + Number(d.value) * counts[d.value], gold: t.gold + Number(d.gold_toz) * counts[d.value] }),
    { notes: 0, goldbacks: 0, gold: 0 },
  ), [chosen, counts]);

  const setCount = (v: string, n: number) => setCounts((c) => ({ ...c, [v]: Math.max(0, Math.min(100000, Math.round(n) || 0)) }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.addGoldbacks({
        state: state.trim(),
        year: year ? Number(year) : null,
        variety: variety.trim() || null,
        acquired_date: acquired || null,
        location_id: location ? Number(location) : null,
        purchase_source: source.trim() || null,
        rows: chosen.map((d) => ({ denomination: d.value, quantity: counts[d.value], price_total: paid[d.value]?.trim() || null })),
      });
      setDone({ ids: r.item_ids, text: `Added ${plural(totals.notes, `${state.trim()} Goldback note`)}.` });
      setCounts({});
      setPaid({});
      await qc.invalidateQueries({ queryKey: ["goldbacks", "summary"] });
      await qc.invalidateQueries({ queryKey: ["items"] });
      await qc.invalidateQueries({ queryKey: ["summary"] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel gb-add" aria-labelledby="gb-add-h">
      <h2 id="gb-add-h">Add Goldbacks</h2>

      <fieldset className="gb-step">
        <legend>Which state or series?</legend>
        <div className="gb-series" role="radiogroup" aria-label="State or series">
          {catalogue.series.map((x) => (
            <button
              key={x.name}
              type="button"
              role="radio"
              aria-checked={state === x.name && !other}
              className={`gb-series-card${state === x.name && !other ? " on" : ""}`}
              onClick={() => { setState(x.name); setOther(false); setYear(""); setDone(null); }}
            >
              <span className="gb-series-name">{x.name}</span>
              <span className="gb-series-year">since {x.first_year}</span>
            </button>
          ))}
          <button type="button" role="radio" aria-checked={other} className={`gb-series-card${other ? " on" : ""}`} onClick={() => { setOther(true); setState(""); setDone(null); }}>
            <span className="gb-series-name">Another</span>
            <span className="gb-series-year">type its name</span>
          </button>
        </div>
        {other && (
          <label className="gb-other">
            Series name
            <input value={state} onChange={(e) => setState(e.target.value)} placeholder="e.g. a new state's series" autoFocus />
          </label>
        )}
      </fieldset>

      {state.trim() && (
        <>
          <fieldset className="gb-step">
            <legend>How many of each?</legend>
            <ul className="gb-denoms">
              {shown.map((d) => {
                const n = counts[d.value] ?? 0;
                return (
                  <li key={d.value} className={`gb-note${n > 0 ? " on" : ""}`}>
                    <span className="gb-note-face" aria-hidden>
                      <span className="gb-note-state">{state.trim()}</span>
                      <span className="gb-note-value">{d.label}</span>
                      <span className="gb-note-word">Goldback{d.label === "1" ? "" : "s"}</span>
                    </span>
                    <span className="gb-note-gold hint tabular">{oz(Number(d.gold_toz))} oz gold</span>
                    <span className="gb-stepper">
                      <button type="button" className="ghost small" aria-label={`One fewer ${d.label}`} disabled={n === 0} onClick={() => setCount(d.value, n - 1)}>−</button>
                      <input
                        type="number"
                        min={0}
                        inputMode="numeric"
                        aria-label={`How many ${d.label} Goldback notes`}
                        value={n || ""}
                        placeholder="0"
                        onChange={(e) => setCount(d.value, Number(e.target.value))}
                      />
                      <button type="button" className="ghost small" aria-label={`One more ${d.label}`} onClick={() => setCount(d.value, n + 1)}>+</button>
                    </span>
                    {n > 0 && (
                      <label className="gb-paid">
                        <span>Paid for these</span>
                        <input inputMode="decimal" value={paid[d.value] ?? ""} onChange={(e) => setPaid((p) => ({ ...p, [d.value]: e.target.value }))} placeholder="optional" aria-label={`Paid for the ${d.label}s, in total`} />
                      </label>
                    )}
                  </li>
                );
              })}
            </ul>
            {!rare && (
              <button type="button" className="ghost small" onClick={() => setRare(true)}>Show the 1/4 and 3 too</button>
            )}
          </fieldset>

          <fieldset className="gb-step gb-more">
            <legend>Anything else? (optional)</legend>
            <label>
              Year
              <select value={year} onChange={(e) => setYear(e.target.value)}>
                <option value="">Not sure</option>
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <label>
              Acquired
              <input type="date" value={acquired} onChange={(e) => setAcquired(e.target.value)} />
            </label>
            <label>
              Stored in
              <select value={location} onChange={(e) => setLocation(e.target.value)}>
                <option value="">Not set</option>
                {(locations.data ?? []).map((l) => <option key={l.id} value={l.id}>{l.path}</option>)}
              </select>
            </label>
            <label>
              Bought from
              <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="Dealer, show, friend…" />
            </label>
            <label>
              Variety
              <input value={variety} onChange={(e) => setVariety(e.target.value)} placeholder="Limited edition, signed…" />
            </label>
          </fieldset>

          <div className="gb-save" role="status">
            <span className="tabular">
              {totals.notes
                ? `${plural(totals.notes, "note")}, ${totals.goldbacks.toLocaleString()} Goldbacks, ${oz(totals.gold)} oz gold`
                : "Choose how many of each denomination you have."}
            </span>
            <button type="button" className="primary" disabled={!totals.notes || busy} onClick={save}>
              {busy ? "Adding…" : totals.notes ? `Add ${plural(totals.notes, "note")}` : "Add"}
            </button>
          </div>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {done && (
        <p className="success" role="status">
          {done.text} {done.ids.length === 1 ? <Link to={`/items/${done.ids[0]}`}>Open it</Link> : <Link to="/?type=goldback">See them</Link>} to add photos or notes.
        </p>
      )}
    </section>
  );
}
