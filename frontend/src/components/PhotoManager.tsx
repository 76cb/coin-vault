import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, Item, LibraryFile, Photo, PhotoRole, ROLE_LABELS } from "../api";
import DropZone from "./DropZone";
import PhotoEditor from "./PhotoEditor";
import PhotoLibrary from "./PhotoLibrary";
import { DuplicateNote, QualityNote } from "./QualityNote";

export default function PhotoManager({ item }: { item: Item }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<Photo[]>([]);
  const [editing, setEditing] = useState<Photo | null>(null);
  const [picking, setPicking] = useState(false);
  const photos = item.photos;
  const refresh = () => qc.invalidateQueries({ queryKey: ["item", item.id] });

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const move = (idx: number, delta: number) => {
    const ids = photos.map((p) => p.id);
    const j = idx + delta;
    if (j < 0 || j >= ids.length) return;
    [ids[idx], ids[j]] = [ids[j], ids[idx]];
    run(() => api.reorderPhotos(item.id, ids));
  };

  const flagged = (p: Photo) => lastUpload.find((u) => u.id === p.id);

  return (
    <section className="photo-manager" aria-label="Photos">
      <DropZone
        disabled={busy}
        label={photos.length ? "Add more photos" : "Add photos"}
        onFiles={(files) =>
          run(async () => {
            const roles: PhotoRole[] | undefined =
              photos.length === 0 && files.length <= 2 ? (["obverse", "reverse"] as PhotoRole[]).slice(0, files.length) : undefined;
            setLastUpload(await api.uploadPhotos(item.id, files, roles));
          })
        }
      />
      <button type="button" className="ghost small pm-library" disabled={busy} onClick={() => setPicking(!picking)}>
        {picking ? "Close your photos" : "Choose from your photos"}
      </button>
      {picking && (
        <LibraryPick
          item={item}
          onAdded={async () => {
            await refresh();
            await qc.invalidateQueries({ queryKey: ["library"] });
            await qc.invalidateQueries({ queryKey: ["items"] });
          }}
        />
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {photos.length > 0 && (
        <ol className="photo-list">
          {photos.map((p, i) => {
            const fresh = flagged(p);
            return (
              <li key={p.id} className={item.cover_photo_id === p.id ? "is-cover" : ""}>
                <a href={p.urls.edited ?? p.urls.original} target="_blank" rel="noreferrer" className="photo-thumb">
                  <img src={p.urls.thumb} alt={`${ROLE_LABELS[p.role]} of ${item.title}`} />
                </a>
                <div className="photo-meta">
                  <select aria-label="Photo role" value={p.role} disabled={busy} onChange={(e) => run(() => api.setPhotoRole(p.id, e.target.value as PhotoRole))}>
                    {Object.entries(ROLE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  <span className="hint">{p.width}×{p.height}{p.edits ? ", edited" : ""}</span>
                  <QualityNote quality={p.quality} />
                  {fresh && <DuplicateNote kind={fresh.duplicate_kind} itemId={fresh.duplicate_of_item_id} />}
                </div>
                <div className="photo-actions">
                  <button type="button" className="ghost small" disabled={busy} onClick={() => setEditing(p)}>Edit</button>
                  <button type="button" className="ghost small" disabled={busy || i === 0} onClick={() => move(i, -1)} aria-label="Move earlier">Up</button>
                  <button type="button" className="ghost small" disabled={busy || i === photos.length - 1} onClick={() => move(i, 1)} aria-label="Move later">Down</button>
                  {item.cover_photo_id === p.id ? (
                    <span className="cover-tag">Cover</span>
                  ) : (
                    <button type="button" className="ghost small" disabled={busy} onClick={() => run(() => api.setCover(item.id, p.id))}>Make cover</button>
                  )}
                  <button
                    type="button"
                    className="ghost small danger"
                    disabled={busy}
                    onClick={() => window.confirm("Delete this photo?") && run(() => api.deletePhoto(p.id))}
                  >
                    Delete
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {editing && (
        <PhotoEditor
          photo={editing}
          title={item.title}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            await refresh();
            await qc.invalidateQueries({ queryKey: ["items"] });
          }}
        />
      )}
    </section>
  );
}

/** Pick a photo you already uploaded (another item's, or one waiting in Upload photos) and add it here. */
function LibraryPick({ item, onAdded }: { item: Item; onAdded: () => Promise<void> }) {
  const [file, setFile] = useState<LibraryFile | null>(null);
  const [role, setRole] = useState<PhotoRole>(item.photos.length ? "other" : "obverse");
  const [cover, setCover] = useState(item.photos.length === 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const add = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.addFromLibrary(item.id, { sha256: file.sha256, role, make_cover: cover });
      await onAdded();
      setNote(`Added ${file.filename ?? "the photo"}.`);
      setFile(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="library-pick">
      <PhotoLibrary selected={file?.sha256 ?? null} onSelect={(f) => { setFile(f); setNote(null); }} exclude={item.photos.map((p) => p.sha256 ?? "")} />
      <div className="library-pick-bar">
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
        <button type="button" className="primary" disabled={!file || busy} onClick={add}>
          {busy ? "Adding…" : file ? "Add this photo" : "Choose a photo above"}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {note && <p className="success">{note}</p>}
    </div>
  );
}
