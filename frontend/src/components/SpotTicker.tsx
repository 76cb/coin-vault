import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ago, api, money } from "../api";

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
  const stale = priced.some((m) => m.stale);
  return (
    <Link to="/dashboard" className="ticker" aria-label="Spot prices per troy ounce">
      {metals.map((m) => (
        <span key={m.metal} className={`tick${m.stale ? " is-stale" : ""}`}>
          <span className="tick-sym">{m.metal}</span>
          <span className="tabular">{m.price ? money(m.price, currency) : "—"}</span>
        </span>
      ))}
      <span className="tick-when">
        {stale ? <span className="badge badge-warn">Stale</span> : !market_open ? <span className="badge">Markets closed</span> : null}
        <span>{ago(newest)}</span>
      </span>
    </Link>
  );
}
