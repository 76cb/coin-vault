import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useCanWrite } from "../access";
import { api, BulkEdit, GAP_LABELS, ITEM_TYPE_LABELS, METAL_LABELS, money, STATUS_LABELS } from "../api";
import Flip from "../components/Flip";

const PAGE_SIZE = 48;

export default function Collection() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const filters = Object.fromEntries(
    ["q", "type", "status", "metal", "location_id", "tag", "missing", "sort", "page", "deleted"].flatMap((k) => (params.get(k) ? [[k, params.get(k)!]] : [])),
  );
  const page = Number(params.get("page") ?? 1);
  const items = useQuery({
    queryKey: ["items", filters],
    queryFn: () => api.items({ ...filters, page_size: String(PAGE_SIZE) }),
    placeholderData: keepPreviousData,
  });
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const qc = useQueryClient();
  const canWrite = useCanWrite();
  // Select mode: tick items, then change them all at once
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkNote, setBulkNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [tagText, setTagText] = useState("");
  const toggle = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  async function bulk(change: Omit<BulkEdit, "ids">, done: string) {
    setBulkBusy(true);
    setBulkNote(null);
    try {
      const r = await api.bulkEdit({ ids: picked, ...change });
      setBulkNote({ ok: true, text: `${r.changed} ${r.changed === 1 ? "item" : "items"} ${done}.` });
      if (change.delete) setPicked([]);
      await Promise.all(["items", "tags", "locations", "summary"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
    } catch (err) {
      setBulkNote({ ok: false, text: (err as Error).message });
    } finally {
      setBulkBusy(false);
    }
  }

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  // the export and the report use the same filters as the list (not its page)
  const exportParams = Object.fromEntries(Object.entries(filters).filter(([k]) => k !== "page"));
  const reportQuery = new URLSearchParams(
    Object.entries(exportParams).filter(([k]) => ["q", "type", "metal", "location_id", "tag"].includes(k)),
  ).toString();
  const total = items.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = Object.keys(filters).some((k) => !["sort", "page"].includes(k));

  return (
    <>
      <div className="page-head">
        <h1>Collection</h1>
        <div className="head-actions">
          <a className="button ghost" href={api.exportCsvUrl(exportParams)} download>Export CSV</a>
          <Link className="button ghost" to={`/report${reportQuery ? `?${reportQuery}` : ""}`}>Insurance report</Link>
          {canWrite && items.data && items.data.items.length > 0 && !params.get("deleted") && (
            <button className={picking ? "" : "ghost"} onClick={() => { setPicking((p) => !p); setPicked([]); setBulkNote(null); }}>
              {picking ? "Done selecting" : "Select"}
            </button>
          )}
          {canWrite && <Link className="button" to="/upload">Upload photos</Link>}
          {canWrite && <Link className="button primary" to="/items/new">Add item</Link>}
        </div>
      </div>

      <div className="filters" role="search">
        <input type="search" aria-label="Search" placeholder="Search title, year, country, cert, a coin in a set…" defaultValue={q} onChange={(e) => update("q", e.target.value)} />
        <select aria-label="Type" value={params.get("type") ?? ""} onChange={(e) => update("type", e.target.value)}>
          <option value="">All types</option>
          {Object.entries(ITEM_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select aria-label="Metal" value={params.get("metal") ?? ""} onChange={(e) => update("metal", e.target.value)}>
          <option value="">Any metal</option>
          {Object.entries(METAL_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select aria-label="Status" value={params.get("status") ?? ""} onChange={(e) => update("status", e.target.value)}>
          <option value="">Any status</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select aria-label="Location" value={params.get("location_id") ?? ""} onChange={(e) => update("location_id", e.target.value)}>
          <option value="">Anywhere</option>
          {locations.data?.map((l) => (
            <option key={l.id} value={l.id}>{l.path}</option>
          ))}
        </select>
        {tags.data && tags.data.length > 0 && (
          <select aria-label="Tag" value={params.get("tag") ?? ""} onChange={(e) => update("tag", e.target.value)}>
            <option value="">Any tag</option>
            {tags.data.map((t) => (
              <option key={t.id} value={t.name}>{t.name}</option>
            ))}
          </select>
        )}
        <select aria-label="Needs attention" value={params.get("missing") ?? ""} onChange={(e) => update("missing", e.target.value)}>
          <option value="">Complete or not</option>
          <option value="any">Needs attention</option>
          {Object.entries(GAP_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <select aria-label="Sort" value={params.get("sort") ?? "updated"} onChange={(e) => update("sort", e.target.value)}>
          <option value="updated">Recently changed</option>
          <option value="created">Recently added</option>
          <option value="title">Title</option>
          <option value="year">Year</option>
          <option value="acquired">Acquired date</option>
          <option value="value">Value, highest first</option>
          <option value="melt">Melt value, highest first</option>
          <option value="gain">Gain, highest first</option>
          <option value="cost">Paid, highest first</option>
        </select>
      </div>

      <p className="count muted">
        {items.isPending ? "Loading…" : `${total} ${total === 1 ? "item" : "items"}`}
        {params.get("deleted") ? " in the bin" : ""}
      </p>

      {items.isError && <p className="error">{(items.error as Error).message}</p>}

      {items.data && items.data.items.length === 0 && (
        <div className="empty">
          {filtered ? (
            <p>{params.get("missing") ? "Nothing here needs attention." : "Nothing matches these filters. Clear the search or pick a different type."}</p>
          ) : (
            <>
              <p>Your collection is empty. Add an item by hand, or upload a batch of photos and turn each pair into an item.</p>
              <div className="head-actions">
                <Link className="button primary" to="/items/new">Add item</Link>
                <Link className="button" to="/upload">Upload photos</Link>
              </div>
            </>
          )}
        </div>
      )}

      {picking && (
        <div className="bulk-bar" role="region" aria-label="Change the selected items">
          <span className="bulk-count">
            <strong>{picked.length}</strong> selected
            <button className="link" onClick={() => setPicked(items.data?.items.map((i) => i.id) ?? [])}>Select all on this page</button>
            {picked.length > 0 && <button className="link" onClick={() => setPicked([])}>Clear</button>}
          </span>
          <select
            aria-label="Move selected to"
            value=""
            disabled={bulkBusy || !picked.length}
            onChange={(e) => e.target.value && bulk({ location_id: e.target.value === "none" ? null : Number(e.target.value) }, "moved")}
          >
            <option value="">Move to…</option>
            <option value="none">No location</option>
            {locations.data?.map((l) => <option key={l.id} value={l.id}>{l.path}</option>)}
          </select>
          <select
            aria-label="Set status of selected"
            value=""
            disabled={bulkBusy || !picked.length}
            onChange={(e) => e.target.value && bulk({ status: e.target.value as "owned" | "for_sale" }, "updated")}
          >
            <option value="">Set status…</option>
            <option value="owned">Owned</option>
            <option value="for_sale">For sale</option>
          </select>
          <span className="bulk-tags">
            <input aria-label="Tag for selected" placeholder="Tag" value={tagText} onChange={(e) => setTagText(e.target.value)} />
            <button className="small" disabled={bulkBusy || !picked.length || !tagText.trim()} onClick={() => bulk({ add_tags: [tagText.trim()] }, "tagged")}>Add tag</button>
            <button className="ghost small" disabled={bulkBusy || !picked.length || !tagText.trim()} onClick={() => bulk({ remove_tags: [tagText.trim()] }, "untagged")}>Remove tag</button>
          </span>
          <button className="ghost small" disabled={bulkBusy || !picked.length} onClick={() => bulk({ verified: true }, "marked as seen today")}>Seen today</button>
          <button
            className="ghost small danger"
            disabled={bulkBusy || !picked.length}
            onClick={() => window.confirm(`Move ${picked.length} ${picked.length === 1 ? "item" : "items"} to the bin? You can restore them later.`) && bulk({ delete: true }, "moved to the bin")}
          >
            Delete
          </button>
          {bulkNote && <span className={bulkNote.ok ? "success" : "error"} role="status">{bulkNote.text}</span>}
        </div>
      )}

      <ul className={`flip-grid${picking ? " picking" : ""}`}>
        {items.data?.items.map((it) => (
          <li key={it.id} className={picked.includes(it.id) ? "picked" : ""}>
            {picking && (
              <label className="pick-box">
                <input type="checkbox" checked={picked.includes(it.id)} onChange={() => toggle(it.id)} aria-label={`Select ${it.title}`} />
              </label>
            )}
            <Link to={`/items/${it.id}`} className="flip-card" onClick={(e) => { if (picking) { e.preventDefault(); toggle(it.id); } }}>
              <Flip src={it.cover_thumb_url} alt={it.title} />
              <span className="flip-title">{it.title}</span>
              <span className="flip-sub">
                {[it.grade, it.coin_count ? `${it.coin_count} coins` : null, it.quantity > 1 ? `×${it.quantity}` : null].filter(Boolean).join("  ")}
              </span>
              {params.get("missing") && it.gaps && it.gaps.length > 0 && (
                <span className="flip-gaps">{it.gaps.map((g) => GAP_LABELS[g]).join(" · ")}</span>
              )}
              {it.matched_coins && it.matched_coins.length > 0 && (
                <span className="flip-contains">
                  Contains {it.matched_coins.slice(0, 2).join(", ")}{it.matched_coins.length > 2 ? ` and ${it.matched_coins.length - 2} more` : ""}
                </span>
              )}
              <span className="flip-foot">
                <span className="flip-values">
                  {it.current && <span className="tabular flip-value" title="Current value">{money(it.current, it.currency)}</span>}
                  <span className="tabular hint" title="What you paid">
                    {it.cost_basis ? `paid ${money(it.cost_basis, it.currency)}` : it.cost_basis_status === "unknown" ? "cost unknown" : ""}
                    {params.get("sort") === "gain" && it.gain ? `, ${Number(it.gain) >= 0 ? "+" : ""}${money(it.gain, it.currency)}` : ""}
                    {params.get("sort") === "melt" && it.melt ? `, melt ${money(it.melt, it.currency)}` : ""}
                  </span>
                </span>
                {it.status !== "owned" && <span className={`status status-${it.status}`}>{STATUS_LABELS[it.status]}</span>}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {pages > 1 && (
        <nav className="pager" aria-label="Pages">
          <button className="ghost" disabled={page <= 1} onClick={() => update("page", String(page - 1))}>Previous</button>
          <span className="muted">Page {page} of {pages}</span>
          <button className="ghost" disabled={page >= pages} onClick={() => update("page", String(page + 1))}>Next</button>
        </nav>
      )}
      <p className="bin-link">
        {params.get("deleted") ? (
          <button className="link" onClick={() => update("deleted", "")}>Back to the collection</button>
        ) : (
          <button className="link" onClick={() => update("deleted", "true")}>Show deleted items</button>
        )}
      </p>
    </>
  );
}
