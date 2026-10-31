import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { api, ITEM_TYPE_LABELS, METAL_LABELS, money, STATUS_LABELS } from "../api";
import Flip from "../components/Flip";

const PAGE_SIZE = 48;

export default function Collection() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const filters = Object.fromEntries(
    ["q", "type", "status", "metal", "location_id", "tag", "sort", "page", "deleted"].flatMap((k) => (params.get(k) ? [[k, params.get(k)!]] : [])),
  );
  const page = Number(params.get("page") ?? 1);
  const items = useQuery({
    queryKey: ["items", filters],
    queryFn: () => api.items({ ...filters, page_size: String(PAGE_SIZE) }),
    placeholderData: keepPreviousData,
  });
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });

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
          <Link className="button" to="/upload">Upload photos</Link>
          <Link className="button primary" to="/items/new">Add item</Link>
        </div>
      </div>

      <div className="filters" role="search">
        <input type="search" aria-label="Search" placeholder="Search title, year, country, cert…" defaultValue={q} onChange={(e) => update("q", e.target.value)} />
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
        <select aria-label="Sort" value={params.get("sort") ?? "updated"} onChange={(e) => update("sort", e.target.value)}>
          <option value="updated">Recently changed</option>
          <option value="created">Recently added</option>
          <option value="title">Title</option>
          <option value="year">Year</option>
          <option value="acquired">Acquired date</option>
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
            <p>Nothing matches these filters. Clear the search or pick a different type.</p>
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

      <ul className="flip-grid">
        {items.data?.items.map((it) => (
          <li key={it.id}>
            <Link to={`/items/${it.id}`} className="flip-card">
              <Flip src={it.cover_thumb_url} alt={it.title} />
              <span className="flip-title">{it.title}</span>
              <span className="flip-sub">
                {[it.grade, it.quantity > 1 ? `×${it.quantity}` : null].filter(Boolean).join("  ")}
              </span>
              <span className="flip-foot">
                <span className="flip-values">
                  {it.current && <span className="tabular flip-value" title="Current value">{money(it.current, it.currency)}</span>}
                  <span className="tabular hint" title="What you paid">
                    {it.cost_basis ? `paid ${money(it.cost_basis, it.currency)}` : it.cost_basis_status === "unknown" ? "cost unknown" : ""}
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
