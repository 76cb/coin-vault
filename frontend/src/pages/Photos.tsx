import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, LibraryFile, PhotoRole, ROLE_LABELS } from "../api";
import PhotoLibrary from "../components/PhotoLibrary";

/** All your photos in one place: see where each is used, and put any of them on an item. */
export default function Photos() {
  const [file, setFile] = useState<LibraryFile | null>(null);
  return (
    <>
      <div className="page-head">
        <h1>Photos</h1>
      </div>
      <p className="muted lede">Every photo you've uploaded, on items or not. Choose one to see where it's used or to put it on an item; the file is shared, not copied.</p>
      <div className={`photos-layout${file ? " has-detail" : ""}`}>
        <PhotoLibrary selected={file?.sha256 ?? null} onSelect={setFile} />
        {file && <PhotoDetail key={file.sha256} file={file} onClose={() => setFile(null)} />}
      </div>
    </>
  );
}

function PhotoDetail({ file, onClose }: { file: LibraryFile; onClose: () => void }) {
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
      <button type="button" className="ghost small" onClick={onClose}>Close</button>
    </aside>
  );
}
