import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useCanWrite } from "../access";
import { api, ImportResult, ITEM_TYPE_LABELS, Metal, METAL_LABELS, money } from "../api";

const day = (d: string) => new Date(d.length === 10 ? `${d}T12:00:00` : d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

function useRun() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}

function Head({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <>
      <p className="crumbs no-print"><Link to="/tools">Tools</Link></p>
      <div className="page-head">
        <h1>{title}</h1>
        {children && <div className="head-actions no-print">{children}</div>}
      </div>
    </>
  );
}

/** Everything that isn't the collection itself, in one place. */
export function Tools() {
  const canWrite = useCanWrite();
  const tools: [string, string, string, boolean][] = [
    ["/checklists", "Series checklists", "Which coins of a series you have and which are missing. Coins inside your mint sets count.", true],
    ["/wants", "Want list", "What you're looking for, with a target price.", true],
    ["/sales", "Sales and gains", "What you've sold, by year: proceeds, cost and gain.", true],
    ["/alerts", "Price alerts", "Be told when gold, silver, platinum or palladium crosses a price you set.", true],
    ["/inventory-check", "Inventory check", "Go through a storage location and tick off each piece as you see it.", canWrite],
    ["/labels", "Storage labels", "Printable labels with a QR code that opens a location's contents on your phone.", true],
    ["/import", "Import a spreadsheet", "Add many items at once from a CSV file.", canWrite],
    ["/report", "Insurance report", "A printable inventory with photos and values.", true],
    ["/?missing=any", "Needs attention", "Items missing their metal, cost, photos or value.", true],
  ];
  return (
    <>
      <div className="page-head"><h1>Tools</h1></div>
      <ul className="tool-grid">
        {tools.filter((t) => t[3]).map(([to, name, what]) => (
          <li key={to}>
            <Link to={to} className="tool-card">
              <strong>{name}</strong>
              <span className="muted">{what}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

// --- Checklists --------------------------------------------------------------------------------------

export function Checklists() {
  const [params, setParams] = useSearchParams();
  const key = params.get("list");
  const all = useQuery({ queryKey: ["checklists"], queryFn: api.checklists });
  if (key) return <ChecklistDetail listKey={key} back={() => setParams({})} />;
  return (
    <>
      <Head title="Series checklists" />
      <p className="muted lede">
        A coin counts when its year, its mint mark (for series collected by mint) and its design's name match: "Oklahoma" or "Morgan" in the title or series.
        Coins listed inside your mint sets count too. Sold items don't.
      </p>
      {all.isPending && <p className="muted">Loading…</p>}
      {all.isError && <p className="error">{(all.error as Error).message}</p>}
      <ul className="checklists">
        {all.data?.map((c) => (
          <li key={c.key}>
            <Link to={`/checklists?list=${c.key}`} className="checklist-card">
              <span className="checklist-name"><strong>{c.name}</strong><span className="tabular">{c.have} of {c.total}</span></span>
              <span className="meter" role="img" aria-label={`${c.have} of ${c.total}`}><span style={{ width: `${(c.have / c.total) * 100}%` }} /></span>
              <span className="hint">{c.note}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

function ChecklistDetail({ listKey, back }: { listKey: string; back: () => void }) {
  const qc = useQueryClient();
  const canWrite = useCanWrite();
  const list = useQuery({ queryKey: ["checklist", listKey], queryFn: () => api.checklist(listKey) });
  const wants = useQuery({ queryKey: ["wants"], queryFn: api.wants });
  const [only, setOnly] = useState<"all" | "missing">("all");
  const { error, run } = useRun();
  const wanted = useMemo(() => new Set((wants.data ?? []).filter((w) => !w.found_at).map((w) => w.title.toLowerCase())), [wants.data]);
  if (list.isPending) return <p className="muted">Loading…</p>;
  if (list.isError) return <p className="error">{(list.error as Error).message}</p>;
  const c = list.data;
  const groups: [string, typeof c.entries][] = [];
  for (const e of c.entries) {
    if (only === "missing" && e.have.length) continue;
    const g = groups.find((x) => x[0] === e.group);
    if (g) g[1].push(e);
    else groups.push([e.group, [e]]);
  }
  return (
    <>
      <p className="crumbs"><Link to="/tools">Tools</Link> › <button className="link" onClick={back}>Series checklists</button></p>
      <div className="page-head">
        <h1>{c.name}</h1>
        <div className="head-actions">
          <div className="segmented" role="radiogroup" aria-label="Show">
            <button role="radio" aria-checked={only === "all"} className={only === "all" ? "on" : ""} onClick={() => setOnly("all")}>All {c.total}</button>
            <button role="radio" aria-checked={only === "missing"} className={only === "missing" ? "on" : ""} onClick={() => setOnly("missing")}>Missing {c.total - c.have}</button>
          </div>
        </div>
      </div>
      <p className="muted lede">You have {c.have} of {c.total}. {c.note}</p>
      {error && <p className="error" role="alert">{error}</p>}
      {groups.length === 0 && <p className="success">Nothing missing: the set is complete.</p>}
      {groups.map(([g, entries]) => (
        <section key={g} className="checklist-group">
          <h2>{g}</h2>
          <ul className="checklist-entries">
            {entries.map((e) => (
              <li key={e.label} className={e.have.length ? "have" : "missing"}>
                <span className="tick" aria-hidden="true">{e.have.length ? "✓" : ""}</span>
                <span className="entry-label">{e.label}</span>
                <span className="entry-have">
                  {e.have.length ? (
                    e.have.map((h, i) => (
                      <span key={h.id}>{i > 0 && ", "}<Link to={`/items/${h.id}`}>{h.in_set ? `in ${h.title}` : h.title}</Link></span>
                    ))
                  ) : wanted.has(e.label.toLowerCase()) ? (
                    <span className="hint">on your want list</span>
                  ) : canWrite ? (
                    <button className="link" onClick={() => run(async () => { await api.createWant({ title: e.label }); await qc.invalidateQueries({ queryKey: ["wants"] }); })}>
                      Add to want list
                    </button>
                  ) : (
                    <span className="hint">missing</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

// --- Want list ---------------------------------------------------------------------------------------

export function Wants() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const canWrite = useCanWrite();
  const wants = useQuery({ queryKey: ["wants"], queryFn: api.wants });
  const [title, setTitle] = useState("");
  const [price, setPrice] = useState("");
  const [notes, setNotes] = useState("");
  const { error, busy, run } = useRun();
  const refresh = () => qc.invalidateQueries({ queryKey: ["wants"] });
  const open = (wants.data ?? []).filter((w) => !w.found_at);
  const found = (wants.data ?? []).filter((w) => w.found_at);
  return (
    <>
      <Head title="Want list" />
      {canWrite && (
        <form
          className="panel want-form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            run(async () => {
              await api.createWant({ title: title.trim(), target_price: price.trim() || null, notes: notes.trim() || null });
              setTitle(""); setPrice(""); setNotes("");
              await refresh();
            });
          }}
        >
          <label className="want-title">What you're looking for<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="1893-S Morgan Dollar, VF or better" required /></label>
          <label>Target price<input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="optional" /></label>
          <label className="want-notes">Notes<input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="optional" /></label>
          <button className="primary" disabled={busy || !title.trim()}>Add to the list</button>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {wants.data && open.length === 0 && <p className="empty">Nothing on the list. Add what you're hunting for, or use "Add to want list" on a series checklist.</p>}
      <ul className="plain-list want-list">
        {open.map((w) => (
          <li key={w.id}>
            <span>
              <strong>{w.title}</strong>
              {w.notes && <span className="hint"> {w.notes}</span>}
            </span>
            <span className="tabular">{w.target_price ? `up to ${money(w.target_price)}` : ""}</span>
            {canWrite && (
              <>
                <button className="small" onClick={() => navigate("/items/new", { state: { want: { id: w.id, title: w.title } } })}>Got it: add the item</button>
                <button className="ghost small" disabled={busy} onClick={() => run(async () => { await api.updateWant(w.id, { found: true }); await refresh(); })}>Mark found</button>
                <button className="ghost small danger" disabled={busy} onClick={() => run(async () => { await api.deleteWant(w.id); await refresh(); })}>Remove</button>
              </>
            )}
          </li>
        ))}
      </ul>
      {found.length > 0 && (
        <>
          <h2>Found</h2>
          <ul className="plain-list want-list">
            {found.map((w) => (
              <li key={w.id}>
                <span>
                  {w.found_item_id ? <Link to={`/items/${w.found_item_id}`}>{w.title}</Link> : w.title}
                  <span className="hint"> found {day(w.found_at!)}</span>
                </span>
                {canWrite && (
                  <>
                    <button className="ghost small" disabled={busy} onClick={() => run(async () => { await api.updateWant(w.id, { found: false }); await refresh(); })}>Still looking</button>
                    <button className="ghost small danger" disabled={busy} onClick={() => run(async () => { await api.deleteWant(w.id); await refresh(); })}>Remove</button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

// --- Sales and gains -----------------------------------------------------------------------------------

const signed = (v: string, cur: string) => `${Number(v) > 0 ? "+" : ""}${money(v, cur)}`;

export function Sales() {
  const [year, setYear] = useState<number | undefined>(undefined);
  const sales = useQuery({ queryKey: ["sales", year ?? "all"], queryFn: () => api.sales(year) });
  if (sales.isPending) return <p className="muted">Loading…</p>;
  if (sales.isError) return <p className="error">{(sales.error as Error).message}</p>;
  const s = sales.data;
  const cur = s.currency;
  return (
    <>
      <Head title="Sales and gains"><button onClick={() => window.print()}>Print</button></Head>
      <p className="muted lede">
        Every item marked as sold: proceeds are the sale price less selling fees, and gain is proceeds less what you paid.
        "Over a year" only says how long you held it. This is a record to hand to whoever prepares your taxes, not tax advice.
      </p>
      {s.years.length === 0 ? (
        <p className="empty">Nothing sold yet. Set an item's status to Sold, with its sale date and price, and it appears here.</p>
      ) : (
        <>
          <table className="figures sales-years">
            <thead>
              <tr><th>Year</th><th>Sold</th><th>Proceeds</th><th>Cost</th><th>Gain</th><th>Held a year or less</th><th>Held over a year</th><th>No purchase date</th><th className="no-print" /></tr>
            </thead>
            <tbody>
              {s.years.map((y) => (
                <tr key={y.year} className={year === y.year ? "on" : ""}>
                  <td><strong>{y.year}</strong></td>
                  <td className="tabular">{y.count}{y.no_cost ? <span className="hint"> ({y.no_cost} with no cost)</span> : null}</td>
                  <td className="tabular">{money(y.proceeds, cur)}</td>
                  <td className="tabular">{money(y.cost, cur)}</td>
                  <td className={`tabular ${Number(y.gain) < 0 ? "is-loss" : ""}`}>{signed(y.gain, cur)}</td>
                  <td className="tabular">{signed(y.gain_short, cur)}</td>
                  <td className="tabular">{signed(y.gain_long, cur)}</td>
                  <td className="tabular">{Number(y.gain_undated) ? signed(y.gain_undated, cur) : "—"}</td>
                  <td className="no-print">
                    <button className="link" onClick={() => setYear(year === y.year ? undefined : y.year)}>{year === y.year ? "Show every year" : `Only ${y.year}`}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2>{year ? `Sold in ${year}` : "Every sale"}</h2>
          <table className="figures">
            <thead>
              <tr><th>Item</th><th>Bought</th><th>Sold</th><th>Proceeds</th><th>Cost</th><th>Gain</th><th>Held</th></tr>
            </thead>
            <tbody>
              {s.sales.map((r) => (
                <tr key={r.id}>
                  <td><Link to={`/items/${r.id}`}>{r.title}</Link>{r.quantity > 1 ? ` ×${r.quantity}` : ""}{r.sale_venue ? <span className="hint"> via {r.sale_venue}</span> : null}</td>
                  <td>{r.acquired_date ? day(r.acquired_date) : <span className="hint">not recorded</span>}</td>
                  <td>{day(r.sale_date)}</td>
                  <td className="tabular">{money(r.proceeds, cur)}{Number(r.sale_fees) ? <span className="hint"> after {money(r.sale_fees, cur)} fees</span> : null}</td>
                  <td className="tabular">{r.cost ? money(r.cost, cur) : <span className="hint">unknown</span>}{r.cost_estimated ? <span className="hint"> est.</span> : null}</td>
                  <td className={`tabular ${r.gain && Number(r.gain) < 0 ? "is-loss" : ""}`}>{r.gain ? signed(r.gain, cur) : "—"}</td>
                  <td>{r.long_term === null ? "—" : r.long_term ? "over a year" : `${r.days_held} days`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}

// --- Price alerts --------------------------------------------------------------------------------------

export function Alerts() {
  const qc = useQueryClient();
  const canWrite = useCanWrite();
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });
  const [metal, setMetal] = useState<Metal>("Ag");
  const [direction, setDirection] = useState<"above" | "below">("below");
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");
  const { error, busy, run } = useRun();
  const refresh = () => qc.invalidateQueries({ queryKey: ["alerts"] });
  return (
    <>
      <Head title="Price alerts" />
      <p className="muted lede">
        Set a price for a metal. When spot reaches it, a notice appears at the top of every page until you dismiss it.
        Prices are checked each time they're fetched (every 15 minutes unless you've changed that), so the app has to be running, but not open.
      </p>
      {canWrite && (
        <form
          className="inline-form panel"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            run(async () => {
              await api.createAlert({ metal, direction, price: price.trim(), note: note.trim() || null });
              setPrice(""); setNote("");
              await refresh();
            });
          }}
        >
          <select aria-label="Metal" value={metal} onChange={(e) => setMetal(e.target.value as Metal)}>
            {Object.entries(METAL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select aria-label="Direction" value={direction} onChange={(e) => setDirection(e.target.value as "above" | "below")}>
            <option value="below">falls to or below</option>
            <option value="above">rises to or above</option>
          </select>
          <input aria-label="Price per ounce" inputMode="decimal" placeholder="Price per ounce" value={price} onChange={(e) => setPrice(e.target.value)} required />
          <input aria-label="Note" placeholder="Note (optional): buy, sell…" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="primary" disabled={busy || !price.trim()}>Add alert</button>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {alerts.data?.length === 0 && <p className="empty">No alerts yet.</p>}
      <ul className="plain-list">
        {alerts.data?.map((a) => (
          <li key={a.id}>
            <span>
              <strong>{METAL_LABELS[a.metal]}</strong> {a.direction === "below" ? "at or below" : "at or above"} {money(a.price, a.currency)}
              {a.note && <span className="hint"> {a.note}</span>}
            </span>
            <span className={a.triggered_at ? "badge-fired" : "hint"}>
              {a.triggered_at ? `Reached ${day(a.triggered_at)} at ${money(a.triggered_price, a.currency)}` : `Waiting; spot is ${money(a.spot, a.currency)}`}
            </span>
            {canWrite && a.triggered_at && (
              <button className="ghost small" disabled={busy} onClick={() => run(async () => { await api.rearmAlert(a.id); await refresh(); })}>Watch again</button>
            )}
            {canWrite && <button className="ghost small danger" disabled={busy} onClick={() => run(async () => { await api.deleteAlert(a.id); await refresh(); })}>Remove</button>}
          </li>
        ))}
      </ul>
    </>
  );
}

// --- Inventory check -----------------------------------------------------------------------------------

const isToday = (iso: string | null | undefined) => {
  if (!iso) return false;
  const t = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return t.toDateString() === new Date().toDateString();
};

export function InventoryCheck() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const loc = params.get("location_id") ?? "";
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const items = useQuery({
    queryKey: ["items", "check", loc],
    queryFn: () => api.items({ ...(loc ? { location_id: loc } : {}), status: "owned", sort: "title", page_size: "200" }),
  });
  const { error, busy, run } = useRun();
  const rows = items.data?.items ?? [];
  // a tick shows at once, before the server has answered
  const [ticked, setTicked] = useState<Record<number, boolean>>({});
  const isSeen = (r: { id: number; verified_at?: string | null }) => ticked[r.id] ?? isToday(r.verified_at);
  const seen = rows.filter(isSeen).length;
  const refresh = () => qc.invalidateQueries({ queryKey: ["items"] });
  return (
    <>
      <Head title="Inventory check" />
      <p className="muted lede">
        Pick a storage location, open it, and tick each piece as you see it. The date is kept on the item as "Last seen", so you can tell when something was last accounted for.
      </p>
      <div className="filters">
        <select aria-label="Location" value={loc} onChange={(e) => setParams(e.target.value ? { location_id: e.target.value } : {})}>
          <option value="">Everything you own</option>
          {locations.data?.map((l) => <option key={l.id} value={l.id}>{l.path} ({l.item_count})</option>)}
        </select>
        <button disabled={busy || !rows.length || seen === rows.length} onClick={() => run(async () => { await api.bulkEdit({ ids: rows.map((r) => r.id), verified: true }); await refresh(); })}>
          Mark all {rows.length} as seen
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {items.data && (
        <p className="count" role="status">
          <strong>{seen} of {rows.length}</strong> seen today{items.data.total > rows.length ? ` (showing the first ${rows.length} of ${items.data.total})` : ""}.
          {rows.length > 0 && seen === rows.length && " All accounted for."}
        </p>
      )}
      {items.data && rows.length === 0 && <p className="empty">Nothing is stored here.</p>}
      <ul className="check-list">
        {rows.map((r) => (
          <li key={r.id} className={isSeen(r) ? "seen" : ""}>
            <label>
              <input
                type="checkbox"
                checked={isSeen(r)}
                onChange={(e) => {
                  const on = e.target.checked;
                  setTicked((t) => ({ ...t, [r.id]: on }));
                  run(async () => {
                    try {
                      await api.verifyItem(r.id, on);
                    } finally {
                      await refresh();
                      setTicked((t) => { const { [r.id]: _, ...rest } = t; return rest; });
                    }
                  });
                }}
              />
              {r.cover_thumb_url ? <img src={r.cover_thumb_url} alt="" /> : <span className="no-thumb" />}
              <span className="check-title">
                <strong>{r.title}</strong>{r.quantity > 1 ? ` ×${r.quantity}` : ""}
                <span className="hint">
                  {[r.grade, r.location_path, r.verified_at ? `last seen ${day(r.verified_at)}` : "never checked"].filter(Boolean).join(" · ")}
                </span>
              </span>
            </label>
            <Link to={`/items/${r.id}`} className="hint">Open</Link>
          </li>
        ))}
      </ul>
    </>
  );
}

// --- Storage labels ------------------------------------------------------------------------------------

export function Labels() {
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const [chosen, setChosen] = useState<number[] | null>(null);
  const all = locations.data ?? [];
  const on = chosen ?? all.map((l) => l.id);
  const link = (id: number) => `${window.location.origin}/?location_id=${id}`;
  return (
    <>
      <Head title="Storage labels"><button className="primary" disabled={!on.length} onClick={() => window.print()}>Print {on.length} {on.length === 1 ? "label" : "labels"}</button></Head>
      <p className="muted lede no-print">
        One label per storage location. Scanning the code with your phone opens that location's contents here (your phone has to be on your home network and signed in).
        The label shows only the location's name, never what's inside.
      </p>
      {locations.data && all.length === 0 && <p className="empty">No storage locations yet. Add them in <Link to="/settings">Settings</Link>.</p>}
      <ul className="label-pick no-print">
        {all.map((l) => (
          <li key={l.id}>
            <label className="check">
              <input type="checkbox" checked={on.includes(l.id)} onChange={(e) => setChosen(e.target.checked ? [...on, l.id] : on.filter((x) => x !== l.id))} />
              {l.path} <span className="hint">{l.item_count} {l.item_count === 1 ? "item" : "items"}</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="label-sheet">
        {all.filter((l) => on.includes(l.id)).map((l) => (
          <div className="label" key={l.id}>
            <img src={api.qrUrl(link(l.id))} alt={`QR code for ${l.path}`} />
            <div>
              <strong>{l.name}</strong>
              {l.path !== l.name && <span>{l.path}</span>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// --- CSV import ----------------------------------------------------------------------------------------

const TEMPLATE = "Title,Quantity,Purchase price,Acquired,Bought from,Location,Tags,Grade,Grading service,Cert number,Notes\r\n"
  + '2023 American Silver Eagle,3,105.00,2023-11-02,Local coin shop,Safe > Box A,stack,,,,\r\n'
  + '1881-S Morgan Dollar,1,85.00,2025-04-12,Coin show,Safe > Box A,,MS63,PCGS,12345678,\r\n';

export function ImportCsv() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const { error, busy, run } = useRun();
  const shown = done ?? preview;
  return (
    <>
      <Head title="Import a spreadsheet" />
      <p className="muted lede">
        Save your spreadsheet as CSV, with the column names in the first row. Only a <strong>Title</strong> column is needed: each title is read the way the
        quick add box reads it, so "2023 American Silver Eagle" gets its kind, year and silver without more columns.
      </p>
      <details className="panel import-help">
        <summary>Columns you can use</summary>
        <p>
          Title, Kind, Quantity, Status, Country, Denomination, Year, Mint mark, Series, Grade, Grading service, Cert number, Serial number, Refiner, Weight,
          Weight unit, Gold ozt, Silver ozt, Platinum ozt, Palladium ozt, Purchase price, Purchase fees, Acquired, Bought from, Location, Tags, Sale date,
          Sale price, Sale fees, Sold through, Notes. These are the names this app's own CSV export uses, so an export can be imported back.
          Common other names work too (Name, Qty, Price, Date, Cert). Locations nest with "&gt;", like "Safe &gt; Box A", and are created if they're new.
          Photos aren't imported.
        </p>
        <p><a href={`data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`} download="coin-vault-import-example.csv">Download an example file</a></p>
      </details>
      <div className="inline-form import-pick">
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV file"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setPreview(null);
            setDone(null);
            if (f) run(async () => setPreview(await api.importItems(f, true)));
          }}
        />
        {preview && !done && preview.ok > 0 && (
          <button
            className="primary"
            disabled={busy}
            onClick={() => file && run(async () => {
              setDone(await api.importItems(file, false));
              await Promise.all(["items", "summary", "locations", "tags"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
            })}
          >
            {busy ? "Importing…" : `Import ${preview.ok} ${preview.ok === 1 ? "item" : "items"}`}
          </button>
        )}
      </div>
      {busy && !shown && <p className="muted" role="status">Reading the file…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {done && (
        <p className="success" role="status">
          {done.created} {done.created === 1 ? "item" : "items"} added. <Link to="/?sort=created">See them in the collection</Link>
          {done.failed > 0 && `; ${done.failed} ${done.failed === 1 ? "row was" : "rows were"} skipped (below).`}
        </p>
      )}
      {preview && !done && (
        <p className="notice" role="status">
          Nothing is saved yet. {preview.ok} {preview.ok === 1 ? "row is" : "rows are"} ready
          {preview.failed > 0 ? `, ${preview.failed} can't be read and will be skipped` : ""}.
          {preview.columns_ignored.length > 0 && ` Columns not used: ${preview.columns_ignored.join(", ")}.`}
        </p>
      )}
      {shown && (
        <table className="figures import-rows">
          <thead>
            <tr><th>Row</th><th>Title</th><th>Kind</th><th>{done ? "Saved with" : "Will be saved with"}</th></tr>
          </thead>
          <tbody>
            {shown.rows.map((r) => (
              <tr key={r.line} className={r.ok ? "" : "bad"}>
                <td className="tabular">{r.line}</td>
                <td>{r.item_id ? <Link to={`/items/${r.item_id}`}>{r.title}</Link> : r.title}</td>
                <td>{r.kind ? ITEM_TYPE_LABELS[r.kind] : ""}</td>
                <td>{r.ok ? r.summary : <span className="is-loss">Skipped: {r.error}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
