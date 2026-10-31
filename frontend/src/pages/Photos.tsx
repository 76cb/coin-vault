import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api, LibraryFile, PhotoRole, ROLE_LABELS } from "../api";
import PhotoLibrary from "../components/PhotoLibrary";

/** Deletes photos everywhere after saying exactly what goes. Returns false if the owner said no. */
async function confirmDelete(files: LibraryFile[]): Promise<boolean> {
  const items = new Map<number, string>();
  files.forEach((f) => f.items.forEach((i) => items.set(i.item_id, i.title)));
  const what = files.length === 1 ? "this photo" : `these ${files.length} photos`;
  const where = items.size
    ? `\n\nThey come off ${items.size === 1 ? "this item" : `these ${items.size} items`}:\n${[...items.values()].slice(0, 12).map((t) => `• ${t}`).join("\n")}${items.size > 12 ? `\n…and ${items.size - 12} more` : ""}`
    : "";
  return window.confirm(`Delete ${what} for good?${where}\n\nThis can't be undone.`);
}

/** All your photos in one place: see where each is used, put any of them on an item, or delete them. */
export default function Photos() {
  const qc = useQueryClient();
  const [file, setFile] = useState<LibraryFile | null>(null);
  const [ticking, setTicking] = useState(false);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [pageFiles, setPageFiles] = useState<LibraryFile[]>([]);
  const known = useRef(new Map<string, LibraryFile>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const onFiles = useCallback((fs: LibraryFile[]) => {
    fs.forEach((f) => known.current.set(f.sha256, f));
    setPageFiles(fs);
  }, []);

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["library"] });
    await qc.invalidateQueries({ queryKey: ["items"] });
    await qc.invalidateQueries({ queryKey: ["item"] });
    await qc.invalidateQueries({ queryKey: ["summary"] });
  };

  const remove = async (shas: string[]) => {
    const files = shas.map((s) => known.current.get(s)).filter(Boolean) as LibraryFile[];
    if (!files.length || !(await confirmDelete(files))) return false;
    setBusy(true);
    setError(null);
    try {
      const r = await api.deleteFromLibrary(shas);
      setNote(`Deleted ${r.deleted} ${r.deleted === 1 ? "photo" : "photos"}${r.photos_removed ? `, taken off ${r.photos_removed} ${r.photos_removed === 1 ? "item photo" : "item photos"}` : ""}.`);
      setTicked(new Set());
      setFile(null);
      await refresh();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const tick = (f: LibraryFile) =>
    setTicked((t) => {
      const n = new Set(t);
      if (n.has(f.sha256)) n.delete(f.sha256);
      else n.add(f.sha256);
      return n;
    });

  return (
    <>
      <div className="page-head">
        <h1>Photos</h1>
        <div className="head-actions">
          <button type="button" className={ticking ? "on" : ""} aria-pressed={ticking} onClick={() => { setTicking(!ticking); setTicked(new Set()); setFile(null); setNote(null); }}>
            {ticking ? "Done selecting" : "Select several"}
          </button>
        </div>
      </div>
      <p className="muted lede">Every photo you've uploaded, on items or not. Choose one to see where it's used, put it on an item, or delete it.</p>
      {ticking && (
        <div className="select-bar" role="region" aria-label="Selected photos">
          <span className="tabular">{ticked.size} selected</span>
          <button type="button" className="ghost small" onClick={() => setTicked(new Set([...ticked, ...pageFiles.map((f) => f.sha256)]))}>Select all on this page</button>
          {ticked.size > 0 && <button type="button" className="ghost small" onClick={() => setTicked(new Set())}>Clear</button>}
          <button type="button" className="danger-solid" disabled={!ticked.size || busy} onClick={() => remove([...ticked])}>
            {busy ? "Deleting…" : `Delete ${ticked.size || ""} ${ticked.size === 1 ? "photo" : "photos"}`.replace("  ", " ")}
          </button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {note && <p className="success" role="status">{note}</p>}
      <div className={`photos-layout${file && !ticking ? " has-detail" : ""}`}>
        <PhotoLibrary selected={file?.sha256 ?? null} onSelect={ticking ? tick : setFile} ticked={ticking ? ticked : undefined} onFiles={onFiles} />
        {file && !ticking && <PhotoDetail key={file.sha256} file={file} onClose={() => setFile(null)} onDelete={() => remove([file.sha256])} busy={busy} />}
      </div>
    </>
  );
}

function PhotoDetail({ file, onClose, onDelete, busy: deleting }: { file: LibraryFile; onClose: () => void; onDelete: () => void; busy: boolean }) {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [itemId, setItemId] = useState<number | null>(null);
  const [role, setRole] = useState<PhotoRole>("obverse");
  const [cover, setCover] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ id: number; title: string } | null>(null);
  const items = useQuery({
    queryKey: ["items", "pick", q],
    queryFn: () => api.items({ q, per_page: "8", sort: "updated" }),
    enabled: q.trim().length > 0,
  });
  const onIt = new Set(file.items.map((i) => i.item_id));
  const picked = items.data?.items.find((i) => i.id === itemId);

  const add = async () => {
    if (!itemId) return;
    setBusy(true);
    setError(null);
    try {
      await api.addFromLibrary(itemId, { sha256: file.sha256, role, make_cover: cover });
      setDone({ id: itemId, title: picked?.title ?? "the item" });
      await qc.invalidateQueries({ queryKey: ["library"] });
      await qc.invalidateQueries({ queryKey: ["items"] });
      await qc.invalidateQueries({ queryKey: ["item", itemId] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="photo-detail" aria-label="Selected photo">
      <a href={file.urls.original} target="_blank" rel="noreferrer" className="photo-detail-img">
        <img src={file.urls.medium} alt={file.filename ?? "Photo"} />
      </a>
      <div className="photo-detail-meta">
        <p><strong>{file.filename ?? "Photo"}</strong></p>
        <p className="hint tabular">{file.width}×{file.height}, {file.bytes >= 1048576 ? `${(file.bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.bytes / 1024))} KB`}, added {new Date(file.created_at).toLocaleDateString()}</p>
        {file.items.length ? (
          <ul className="photo-uses">
            {file.items.map((i) => (
              <li key={i.photo_id}>
                <Link to={`/items/${i.item_id}`}>{i.title}</Link>
                <span className="hint"> {ROLE_LABELS[i.role].toLowerCase()}{i.is_cover ? ", cover" : ""}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">{file.waiting_upload ? <>Waiting in <Link to="/upload">Upload photos</Link>; not on an item yet.</> : "Not on an item."}</p>
        )}
      </div>

      <div className="photo-put">
        <h2>Put it on an item</h2>
        <label>
          Find the item
          <input value={q} onChange={(e) => { setQ(e.target.value); setItemId(null); setDone(null); }} placeholder="Title, year, country…" />
        </label>
        {items.data && (
          items.data.items.length ? (
            <ul className="item-pick" role="listbox" aria-label="Items">
              {items.data.items.map((i) => (
                <li key={i.id}>
                  <button type="button" role="option" aria-selected={itemId === i.id} className={itemId === i.id ? "is-selected" : ""} disabled={onIt.has(i.id)} onClick={() => setItemId(i.id)}>
                    {i.cover_thumb_url ? <img src={i.cover_thumb_url} alt="" /> : <span className="item-pick-empty" />}
                    <span>{i.title}{onIt.has(i.id) ? <span className="hint"> (already has it)</span> : null}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">No items match.</p>
          )
        )}
        {itemId && (
          <div className="photo-put-opts">
            <label>
              As
              <select value={role} onChange={(e) => setRole(e.target.value as PhotoRole)}>
                {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={cover} onChange={(e) => setCover(e.target.checked)} />
              Make it the cover photo
            </label>
            <button type="button" className="primary" disabled={busy} onClick={add}>{busy ? "Adding…" : "Add to item"}</button>
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        {done && <p className="success">Added to <Link to={`/items/${done.id}`}>{done.title}</Link>.</p>}
      </div>
      <div className="photo-detail-foot">
        <button type="button" className="ghost small" onClick={onClose}>Close</button>
        <button type="button" className="ghost small danger" disabled={deleting} onClick={onDelete}>
          {deleting ? "Deleting…" : file.items.length > 1 ? `Delete from all ${file.items.length} items` : "Delete photo"}
        </button>
      </div>
    </aside>
  );
}
