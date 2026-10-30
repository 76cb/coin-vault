import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, Item, Photo, PhotoRole, ROLE_LABELS } from "../api";
import DropZone from "./DropZone";
import { DuplicateNote, QualityNote } from "./QualityNote";

export default function PhotoManager({ item }: { item: Item }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<Photo[]>([]);
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
      {error && <p className="error" role="alert">{error}</p>}
      {photos.length > 0 && (
        <ol className="photo-list">
          {photos.map((p, i) => {
            const fresh = flagged(p);
            return (
              <li key={p.id} className={item.cover_photo_id === p.id ? "is-cover" : ""}>
                <a href={p.urls.original} target="_blank" rel="noreferrer" className="photo-thumb">
                  <img src={p.urls.thumb} alt={`${ROLE_LABELS[p.role]} of ${item.title}`} />
                </a>
                <div className="photo-meta">
                  <select aria-label="Photo role" value={p.role} disabled={busy} onChange={(e) => run(() => api.setPhotoRole(p.id, e.target.value as PhotoRole))}>
                    {Object.entries(ROLE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  <span className="hint">{p.width}×{p.height}</span>
                  <QualityNote quality={p.quality} />
                  {fresh && <DuplicateNote kind={fresh.duplicate_kind} itemId={fresh.duplicate_of_item_id} />}
                </div>
                <div className="photo-actions">
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
    </section>
  );
}
