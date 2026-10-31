import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, LibraryFile } from "../api";

export type LibraryShow = "all" | "on_items" | "not_on_items";
const SHOWS: [LibraryShow, string][] = [["all", "All"], ["on_items", "On items"], ["not_on_items", "Not on an item"]];
const PER_PAGE = 60;

/** Every photo you've uploaded, each once, newest first. Click one to choose it. */
export default function PhotoLibrary({
  selected,
  onSelect,
  exclude = [],
  initialShow = "all",
}: {
  selected: string | null;
  onSelect: (f: LibraryFile) => void;
  exclude?: string[]; // files already on the item being edited
  initialShow?: LibraryShow;
}) {
  const [show, setShow] = useState<LibraryShow>(initialShow);
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["library", show, page], queryFn: () => api.library(show, page, PER_PAGE) });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / PER_PAGE)) : 1;

  return (
    <div className="library">
      <div className="library-bar">
        <div className="segmented" role="radiogroup" aria-label="Which photos">
          {SHOWS.map(([v, label]) => (
            <button key={v} type="button" role="radio" aria-checked={show === v} className={show === v ? "on" : ""} onClick={() => { setShow(v); setPage(1); }}>
              {label}
            </button>
          ))}
        </div>
        {q.data && <span className="hint">{q.data.total.toLocaleString()} {q.data.total === 1 ? "photo" : "photos"}</span>}
      </div>
      {q.isPending && <p className="muted">Loading photos…</p>}
      {q.isError && <p className="error">{(q.error as Error).message}</p>}
      {q.data && q.data.files.length === 0 && (
        <p className="muted">{show === "not_on_items" ? "Every photo you've uploaded is on an item." : "No photos yet. Add some on an item, or with Upload photos."}</p>
      )}
      {q.data && q.data.files.length > 0 && (
        <ul className="library-grid">
          {q.data.files.map((f) => {
            const already = exclude.includes(f.sha256);
            return (
              <li key={f.sha256}>
                <button
                  type="button"
                  className={`library-tile${selected === f.sha256 ? " is-selected" : ""}`}
                  aria-pressed={selected === f.sha256}
                  disabled={already}
                  onClick={() => onSelect(f)}
                  title={already ? "Already on this item" : f.filename ?? undefined}
                >
                  <img src={f.urls.thumb} alt={f.filename ?? "Photo"} loading="lazy" />
                  <span className="library-caption">
                    {already ? "On this item" : f.items.length ? f.items.map((i) => i.title).join(", ") : f.waiting_upload ? "Waiting in uploads" : "Not on an item"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {pages > 1 && (
        <div className="library-pages">
          <button type="button" className="ghost small" disabled={page <= 1} onClick={() => setPage(page - 1)}>Newer</button>
          <span className="hint tabular">Page {page} of {pages}</span>
          <button type="button" className="ghost small" disabled={page >= pages} onClick={() => setPage(page + 1)}>Older</button>
        </div>
      )}
    </div>
  );
}
