import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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
  ticked,
  onFiles,
  remember,
}: {
  selected: string | null;
  onSelect: (f: LibraryFile) => void;
  ticked?: Set<string>; // selecting several: these are ticked, and a click ticks or unticks
  onFiles?: (files: LibraryFile[]) => void; // the photos on the current page
  exclude?: string[]; // files already on the item being edited
  initialShow?: LibraryShow;
  remember?: string; // keep the All / On items / Not on an item choice for this browser tab under this name
}) {
  const [show, setShowState] = useState<LibraryShow>(() => {
    try {
      const v = remember ? sessionStorage.getItem(`cv-library-${remember}`) : null;
      return v && SHOWS.some(([k]) => k === v) ? (v as LibraryShow) : initialShow;
    } catch {
      return initialShow;
    }
  });
  const setShow = (v: LibraryShow) => {
    setShowState(v);
    try {
      if (remember) sessionStorage.setItem(`cv-library-${remember}`, v);
    } catch {
      /* not remembered */
    }
  };
  const order = ticked ? [...ticked] : [];
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["library", show, page], queryFn: () => api.library(show, page, PER_PAGE) });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / PER_PAGE)) : 1;
  useEffect(() => { if (q.data && onFiles) onFiles(q.data.files); }, [q.data, onFiles]);

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
            const on = ticked ? ticked.has(f.sha256) : selected === f.sha256;
            return (
              <li key={f.sha256}>
                <button
                  type="button"
                  className={`library-tile${on ? " is-selected" : ""}${ticked ? " is-ticking" : ""}`}
                  aria-pressed={on}
                  disabled={already}
                  onClick={() => onSelect(f)}
                  title={already ? "Already on this item" : f.filename ?? undefined}
                >
                  {ticked && <span className={`library-tick${on ? " on" : ""}`} aria-hidden>{on ? order.indexOf(f.sha256) + 1 : ""}</span>}
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
