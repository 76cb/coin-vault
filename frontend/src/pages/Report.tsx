import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, ITEM_TYPE_LABELS, ItemType, Metal, METAL_LABELS, money, ReportItem, ReportOrder } from "../api";

const ORDERS: [ReportOrder, string][] = [
  ["value", "Highest value first"],
  ["location", "By location"],
  ["title", "By title"],
  ["acquired", "By date acquired"],
];

const longDate = (d: string) => new Date(d.length === 10 ? `${d}T12:00:00` : d).toLocaleDateString(undefined, { dateStyle: "long" });
const shortDate = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" });
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

function loadPref(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(`cv-report-${key}`);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}
function savePref(key: string, on: boolean) {
  try {
    localStorage.setItem(`cv-report-${key}`, on ? "1" : "0");
  } catch {
    /* private window: the choice just isn't remembered */
  }
}

/** A printable inventory of what you hold, for an insurer or appraiser: photos, descriptions, identifying numbers and values. */
export default function Report() {
  const [params] = useSearchParams();
  const filters = Object.fromEntries(["q", "type", "metal", "location_id", "tag"].flatMap((k) => (params.get(k) ? [[k, params.get(k)!]] : [])));
  const [order, setOrder] = useState<ReportOrder>("value");
  const [photos, setPhotosState] = useState(() => loadPref("photos", true));
  const [paid, setPaidState] = useState(() => loadPref("paid", false));
  const setPhotos = (on: boolean) => { setPhotosState(on); savePref("photos", on); };
  const setPaid = (on: boolean) => { setPaidState(on); savePref("paid", on); };
  const q = useQuery({ queryKey: ["report", filters, order], queryFn: () => api.report({ ...filters, order }), placeholderData: keepPreviousData });
  const r = q.data;
  const cur = r?.currency ?? "USD";
  const filterWords = [
    filters.metal ? METAL_LABELS[filters.metal as Metal] : "",
    filters.type ? ITEM_TYPE_LABELS[filters.type as ItemType] : "",
    filters.q ? `matching “${filters.q}”` : "",
    filters.tag ? `tagged ${filters.tag}` : "",
    filters.location_id ? "in one location" : "",
  ].filter(Boolean);

  return (
    <div className={`report${photos ? "" : " no-photos"}`}>
      <div className="report-tools" role="group" aria-label="Report options">
        <div className="report-tools-row">
          <Link to={`/${filterWords.length ? `?${new URLSearchParams(filters)}` : ""}`}>Back to the collection</Link>
          <button type="button" className="primary" onClick={() => window.print()} disabled={!r}>Print or save as PDF</button>
        </div>
        <div className="report-tools-row">
          <label>
            Order
            <select value={order} onChange={(e) => setOrder(e.target.value as ReportOrder)}>
              {ORDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={photos} onChange={(e) => setPhotos(e.target.checked)} /> Photos</label>
          <label className="check"><input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} /> What I paid</label>
        </div>
        {filterWords.length > 0 && (
          <p className="hint">
            Only items that are {filterWords.join(", ")}, from the Collection page's filters. <Link to="/report">Include everything</Link>
          </p>
        )}
        <p className="hint">To save a PDF, choose “Save as PDF” as the printer. Sold items are left out.</p>
      </div>

      {q.isPending && <p className="muted">Loading…</p>}
      {q.isError && <p className="error">{(q.error as Error).message}</p>}
      {r && (
        <article className={`report-doc${q.isFetching ? " refetching" : ""}`} aria-labelledby="report-title">
          <header className="report-head">
            <h1 id="report-title">Collection inventory</h1>
            <p>
              Prepared for {r.owner} on {longDate(r.date)}.
              {filterWords.length > 0 && <> Only items that are {filterWords.join(", ")}.</>}
            </p>
          </header>

          <section className="report-summary" aria-label="Summary">
            <div className="report-total">
              <span>Total value</span>
              <strong className="tabular">{money(r.current, cur)}</strong>
            </div>
            <dl>
              <div><dt>Items</dt><dd>{plural(r.count, "item")}{r.pieces !== r.count ? `, ${plural(r.pieces, "piece")}` : ""}</dd></div>
              {paid && <div><dt>Paid</dt><dd className="tabular">{money(r.cost, cur)}{r.cost_items < r.count ? ` (${r.cost_items} of ${r.count} items)` : ""}</dd></div>}
              <div><dt>Metal at spot</dt><dd className="tabular">{money(r.melt, cur)}</dd></div>
              {r.spot.length > 0 && (
                <div>
                  <dt>Spot prices used</dt>
                  <dd>{r.spot.map((s) => `${s.label} ${money(s.price, cur)}/ozt`).join(", ")}{r.spot[0].price_time ? `, ${longDate(r.spot[0].price_time)}` : ""}</dd>
                </div>
              )}
            </dl>
            <p className="report-method">
              Each value is the item's market value where one has been recorded (dated, with its source), otherwise the value of its metal at
              the spot prices above, whichever the item is set to use.{r.unvalued > 0 ? ` ${plural(r.unvalued, "item has", "items have")} no value yet and ${r.unvalued === 1 ? "is" : "are"} not in the total.` : ""}
            </p>
          </section>

          {r.by_location.length > 1 && (
            <section className="report-section" aria-labelledby="report-loc">
              <h2 id="report-loc">By location</h2>
              <table className="report-table report-locations">
                <thead><tr><th>Location</th><th>Items</th><th>Value</th></tr></thead>
                <tbody>
                  {r.by_location.map((g) => (
                    <tr key={g.label}><td>{g.label}</td><td className="tabular">{g.count}</td><td className="tabular">{money(g.current, cur)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section className="report-section" aria-labelledby="report-items">
            <h2 id="report-items">Items</h2>
            {r.items.length === 0 ? (
              <p className="muted">Nothing to list{filterWords.length ? " with these filters" : ""}.</p>
            ) : (
              <table className="report-table report-items">
                <thead>
                  <tr>
                    <th className="col-n">No.</th>
                    {photos && <th className="col-photo">Photo</th>}
                    <th>Item</th>
                    <th className="col-where">Location and date</th>
                    {paid && <th className="col-money">Paid</th>}
                    <th className="col-money">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {r.items.map((it, i) => <Row key={it.id} n={i + 1} it={it} cur={cur} photos={photos} paid={paid} />)}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2 + (photos ? 1 : 0) + 1}>Total, {plural(r.count, "item")}</td>
                    {paid && <td className="tabular col-money">{money(r.cost, cur)}</td>}
                    <td className="tabular col-money">{money(r.current, cur)}</td>
                  </tr>
                </tfoot>
              </table>
            )}
          </section>

          <footer className="report-foot">
            Made with Coin Vault on {new Date(r.generated_at).toLocaleString(undefined, { dateStyle: "long", timeStyle: "short" })}. Values are
            estimates from recorded market values and spot prices, not a professional appraisal.
          </footer>
        </article>
      )}
    </div>
  );
}

function Row({ it, n, cur, photos, paid }: { it: ReportItem; n: number; cur: string; photos: boolean; paid: boolean }) {
  return (
    <tr>
      <td className="col-n tabular">{n}</td>
      {photos && (
        <td className="col-photo">
          {it.photos.length > 0 ? (
            <span className={`report-photos${it.kind === "Coin" || it.kind === "Bullion" ? " round" : ""}`}>{it.photos.map((u) => <img key={u} src={u} alt="" loading="eager" />)}</span>
          ) : (
            <span className="hint">No photo</span>
          )}
        </td>
      )}
      <td>
        <strong className="report-title">{it.quantity > 1 ? `${it.quantity} × ` : ""}{it.title}</strong>
        {it.description && it.description.toLowerCase() !== it.title.toLowerCase() && <span className="report-line">{it.description}</span>}
        <span className="report-line">
          {[it.kind, it.grade, it.metals].filter(Boolean).join(", ")}
        </span>
        {it.identifiers.length > 0 && <span className="report-line report-ids">{it.identifiers.join("; ")}</span>}
      </td>
      <td className="col-where">
        {it.location ?? <span className="hint">No location</span>}
        {it.acquired_date && <span className="report-line">Acquired {shortDate(it.acquired_date)}</span>}
      </td>
      {paid && <td className="col-money tabular">{it.cost ? money(it.cost, cur) : "—"}</td>}
      <td className="col-money tabular">
        {it.current ? money(it.current, cur) : "—"}
        {it.current_each && <span className="report-line">{money(it.current_each, cur)} each</span>}
        <span className="report-line report-basis">{it.basis}</span>
      </td>
    </tr>
  );
}
