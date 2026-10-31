import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ago, api, Bucket, compactMoney, Metal, METAL_LABELS, money, Spot } from "../api";
import LineChart from "../components/LineChart";

const RANGES: [number, string][] = [
  [1, "Day"],
  [7, "Week"],
  [30, "Month"],
  [90, "3 months"],
  [365, "Year"],
];

/** Prices more than a day old while flagged stale: worth explaining, not just badging. */
function oldPrices(metals: Spot[]): Spot[] {
  return metals.filter((m) => m.price && m.stale && m.price_time && Date.now() - new Date(m.price_time).getTime() > 86_400_000);
}

function toz(v: string | number): string {
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 3 })} ozt`;
}

export default function Dashboard() {
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: 120_000 });
  const refresh = useMutation({
    mutationFn: api.refreshSpot,
    onSuccess: async (r) => {
      qc.setQueryData(["spot"], r.latest);
      await qc.invalidateQueries({ queryKey: ["summary"] });
      await qc.invalidateQueries({ queryKey: ["history"] });
      await qc.invalidateQueries({ queryKey: ["items"] });
    },
  });

  if (summary.isPending) return <p className="muted">Loading…</p>;
  if (summary.isError) return <p className="error">{(summary.error as Error).message}</p>;
  const s = summary.data;
  const t = s.totals;
  const cur = s.currency;
  const priced = s.spot.metals.filter((m) => m.price);
  const old = oldPrices(s.spot.metals);
  const newest = priced.map((m) => m.fetched_at!).sort().at(-1);
  const heldMetals = (Object.keys(METAL_LABELS) as Metal[]).filter((m) => Number(s.pure_toz[m] ?? 0) > 0);

  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
        <div className="head-actions">
          <button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? "Fetching prices…" : "Refresh spot prices"}
          </button>
        </div>
      </div>
      {refresh.data && !refresh.data.ok && (
        <p className="error" role="alert">Couldn't fetch prices: {refresh.data.errors.join("; ") || "no provider available"}.</p>
      )}
      {refresh.isError && <p className="error" role="alert">{(refresh.error as Error).message}</p>}
      {old.length > 0 && (
          <p className="notice">
            The {old.map((m) => `${METAL_LABELS[m.metal].toLowerCase()} (from ${new Date(m.price_time!).toLocaleDateString(undefined, { month: "short", day: "numeric" })})`).join(" and ")}{" "}
            {old.length === 1 ? "price is" : "prices are"} out of date, so melt values for {old.length === 1 ? "it" : "them"} are approximate.
            gold-api.com's platinum and palladium prices have stopped updating; a free Metal Sentinel or Metals.Dev key in <Link to="/settings#providers">Settings</Link> supplies current ones.
          </p>
      )}

      {priced.length === 0 && (
        <p className="notice">
          No spot prices have been fetched yet, so melt values can't be worked out. Press <strong>Refresh spot prices</strong>, or check the
          price providers in <Link to="/settings#prices">Settings</Link>.
        </p>
      )}

      <section className="hero" aria-labelledby="hero-label">
        <p id="hero-label" className="hero-label">Collection value</p>
        <p className="hero-value">{money(t.current, cur)}</p>
        <p className="hero-sub">
          {t.item_count} {t.item_count === 1 ? "item" : "items"}, {t.pieces} {t.pieces === 1 ? "piece" : "pieces"}.{" "}
          {t.valued_at_market > 0
            ? `${t.valued_at_market} valued at market, the rest at melt${newest ? ` using spot prices from ${ago(newest)}` : ""}.`
            : `Valued at melt${newest ? ` using spot prices from ${ago(newest)}` : ""}; add market values on each item.`}
          {t.no_value_items > 0 && ` ${t.no_value_items} ${t.no_value_items === 1 ? "has" : "have"} no value yet.`}
        </p>
      </section>

      <dl className="ledger-row">
        <div>
          <dt>Melt</dt>
          <dd>{money(t.melt, cur)}</dd>
          <span className="hint">metal at spot</span>
        </div>
        <div>
          <dt>Market</dt>
          <dd>{t.market_items ? money(t.market, cur) : "—"}</dd>
          <span className="hint">{t.market_items ? `${t.market_items} ${t.market_items === 1 ? "item" : "items"} with a market value` : "none entered yet"}</span>
        </div>
        <div>
          <dt>Paid</dt>
          <dd>{money(t.cost, cur)}</dd>
          <span className="hint">
            {t.estimated_cost_items > 0 ? `${money(t.cost_estimated, cur)} estimated. ` : ""}
            {t.cost_unknown_items > 0 ? `${t.cost_unknown_items} without a cost.` : "Every item has a cost."}
          </span>
        </div>
        <div>
          <dt>Gain</dt>
          <dd className={Number(t.gain) < 0 ? "is-loss" : "is-gain"}>
            {Number(t.gain) > 0 ? "+" : ""}
            {money(t.gain, cur)}
          </dd>
          <span className="hint">on {t.gain_items} {t.gain_items === 1 ? "item" : "items"} with a cost</span>
        </div>
      </dl>

      {heldMetals.length > 0 && (
        <dl className="ledger-row ledger-metals">
          {heldMetals.map((m) => (
            <div key={m}>
              <dt>{METAL_LABELS[m]}</dt>
              <dd>{toz(s.pure_toz[m])}</dd>
              <span className="hint">pure, {money(s.by_metal.find((b) => b.key === m)?.melt ?? "0", cur)} at spot</span>
            </div>
          ))}
        </dl>
      )}

      <SpotChart currency={cur} held={heldMetals} />

      <div className="breakdowns">
        <Breakdown title="By metal" buckets={s.by_metal} currency={cur} />
        <Breakdown title="By type" buckets={s.by_type} currency={cur} />
        <Breakdown title="By location" buckets={s.by_location} currency={cur} />
      </div>
    </>
  );
}

function SpotChart({ currency, held }: { currency: string; held: Metal[] }) {
  const [metal, setMetal] = useState<Metal>(held[0] ?? "Ag");
  const [days, setDays] = useState(30);
  const [mode, setMode] = useState<"holdings" | "price">(held.length ? "holdings" : "price");
  const hist = useQuery({
    queryKey: ["history", metal, days],
    queryFn: () => api.spotHistory(metal, days),
    placeholderData: keepPreviousData,
  });
  const h = hist.data;
  const holdings = Number(h?.holdings_toz ?? 0);
  const showHoldings = mode === "holdings" && holdings > 0;
  const points = (h?.points ?? []).map((p) => ({ t: new Date(p.t).getTime(), v: Number(p.price) * (showHoldings ? holdings : 1) }));
  const fmtTime = (t: number) =>
    new Date(t).toLocaleString(undefined, days <= 2 ? { hour: "numeric", minute: "2-digit" } : days <= 90 ? { month: "short", day: "numeric" } : { month: "short", year: "2-digit" });
  const fmtTip = (t: number) => new Date(t).toLocaleString(undefined, { dateStyle: "medium", timeStyle: days <= 31 ? "short" : undefined });
  const title = showHoldings
    ? `Your ${METAL_LABELS[metal].toLowerCase()} (${toz(holdings)}) at spot`
    : `${METAL_LABELS[metal]} spot price per troy ounce`;

  return (
    <section className="panel chart-panel" aria-labelledby="chart-title">
      <div className="chart-controls">
        <div className="segmented" role="radiogroup" aria-label="Metal">
          {(Object.keys(METAL_LABELS) as Metal[]).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={metal === m} className={metal === m ? "on" : ""} onClick={() => setMetal(m)}>
              {METAL_LABELS[m]}
            </button>
          ))}
        </div>
        <select aria-label="Time range" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {RANGES.map(([d, l]) => <option key={d} value={d}>{l}</option>)}
        </select>
        <select aria-label="Show" value={mode} onChange={(e) => setMode(e.target.value as "holdings" | "price")}>
          <option value="holdings">Value of what you hold</option>
          <option value="price">Price per ounce</option>
        </select>
      </div>
      <h2 id="chart-title">{title}</h2>
      {mode === "holdings" && holdings === 0 && h && (
        <p className="hint">You don't hold any {METAL_LABELS[metal].toLowerCase()}, so this shows the price per ounce.</p>
      )}
      <div className={hist.isFetching ? "refetching" : ""}>
        {points.length >= 2 ? (
          <>
            <LineChart points={points} label={title} format={(v) => compactMoney(v, currency)} formatTime={fmtTime} formatTip={fmtTip} />
            {showHoldings && <p className="hint">Uses what you hold today at each past price, so changes are price movement only.</p>}
            <details className="chart-table">
              <summary>Show the numbers</summary>
              <table className="figures">
                <thead><tr><th>When</th><th>{showHoldings ? "Value" : "Price per ozt"}</th></tr></thead>
                <tbody>
                  {points.slice(-30).reverse().map((p) => (
                    <tr key={p.t}><td>{fmtTip(p.t)}</td><td className="tabular">{money(String(p.v), currency)}</td></tr>
                  ))}
                </tbody>
              </table>
              {points.length > 30 && <p className="hint">The latest 30 of {points.length}.</p>}
            </details>
          </>
        ) : (
          <p className="chart-empty muted">
            {hist.isPending ? "Loading…" : "Not enough price history for this range yet. A price is recorded every time the app polls, so the chart fills in over the next hours."}
          </p>
        )}
      </div>
    </section>
  );
}

function Breakdown({ title, buckets, currency }: { title: string; buckets: Bucket[]; currency: string }) {
  const max = Math.max(0, ...buckets.map((b) => Number(b.current)));
  return (
    <section className="panel">
      <h2>{title}</h2>
      {buckets.length === 0 ? (
        <p className="muted">Nothing yet.</p>
      ) : (
        <ul className="bars">
          {buckets.map((b) => {
            const v = Number(b.current);
            const pct = max > 0 ? (v / max) * 100 : 0;
            const tip = `${b.label}: ${money(b.current, currency)}, ${b.count} ${b.count === 1 ? "item" : "items"}${Number(b.cost) ? `, paid ${money(b.cost, currency)}` : ""}`;
            return (
              <li key={b.key} title={tip} tabIndex={0} aria-label={tip}>
                <span className="bar-label">
                  <span>{b.label}</span>
                  <span className="hint">{b.count} {b.count === 1 ? "item" : "items"}</span>
                </span>
                <span className="bar-track">
                  {v > 0 && <span className="bar" style={{ width: `${Math.max(pct, 1) * 0.72}%` }} />}
                  <span className="bar-value tabular">{v > 0 ? compactMoney(v, currency) : "No value yet"}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
