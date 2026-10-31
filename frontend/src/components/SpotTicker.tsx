import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ago, api, METAL_LABELS, money } from "../api";

const SOURCES: Record<string, string> = { gold_api: "gold-api.com", metal_sentinel: "Metal Sentinel", metals_dev: "Metals.Dev" };

/** Spot prices in the header: price per troy ounce, when it was fetched, and whether it is stale. */
export default function SpotTicker() {
  const spot = useQuery({ queryKey: ["spot"], queryFn: api.spotLatest, refetchInterval: 60_000 });
  if (!spot.data) return null;
  const { metals, currency, market_open } = spot.data;
  const priced = metals.filter((m) => m.price);
  if (priced.length === 0) {
    return (
      <Link to="/settings#prices" className="ticker ticker-empty">No spot prices yet</Link>
    );
  }
  const newest = priced.map((m) => m.fetched_at!).sort().at(-1)!;
  const stale = metals.filter((m) => m.stale);
  return (
    <Link to="/dashboard" className="ticker" aria-label="Spot prices per troy ounce">
      {metals.map((m) => (
        <span
          key={m.metal}
          className={`tick${m.stale ? " is-stale" : ""}`}
          title={m.price ? `${METAL_LABELS[m.metal]}: price from ${ago(m.price_time)}, via ${SOURCES[m.source ?? ""] ?? m.source}${m.stale ? " (out of date)" : ""}` : `${METAL_LABELS[m.metal]}: no price yet`}
        >
          <span className="tick-sym">{m.metal}</span>
          <span className="tabular">{m.price ? money(m.price, currency) : "—"}</span>
        </span>
      ))}
      <span className="tick-when">
        {stale.length > 0 && <span className="badge badge-warn">{stale.length === metals.length ? "Stale" : `Old: ${stale.map((m) => m.metal).join(", ")}`}</span>}
        {!market_open && <span className="badge">Markets closed</span>}
        <span>{ago(newest)}</span>
      </span>
    </Link>
  );
}
