import { useQueryClient } from "@tanstack/react-query";
import { ReactNode, useCallback, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api, Described, PhotoRole, PickedPhoto, ROLE_LABELS } from "../api";
import { AiIdentify, useAiReady } from "../components/Ai";
import ItemForm, { defaultsFromDescription, FormState } from "../components/ItemForm";
import QuickStart, { AfterSave } from "../components/QuickStart";

export default function NewItem() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const carried = useLocation().state as { photos?: PickedPhoto[]; described?: Described } | null;
  // details the AI already read on the Upload page arrive filled in
  const [seed, setSeed] = useState<{ n: number; defaults: Partial<FormState>; after?: AfterSave } | null>(
    carried?.described ? { n: 1, defaults: defaultsFromDescription(carried.described) } : null,
  );
  const use = useCallback((defaults: Partial<FormState>, after?: AfterSave) => setSeed({ n: Date.now(), defaults, after }), []);
  const [photos, setPhotos] = useState<PickedPhoto[]>(carried?.photos ?? []);
  const ai = useAiReady();
  return (
    <>
      <div className="page-head">
        <h1>Add item</h1>
      </div>
      {photos.length > 0 && (
        <ChosenPhotos photos={photos} onChange={setPhotos}>
          {ai && <AiIdentify photos={photos.map((p) => ({ sha256: p.sha256, role: p.role }))} onUse={use} />}
        </ChosenPhotos>
      )}
      {carried?.described && seed?.n === 1 && <p className="success">Filled in from what the AI read on the photos. Check it, add what you paid, and save.</p>}
      <QuickStart onUse={use} />
      <p className="muted lede">
        Or fill in the form yourself. Only the title is required
        {photos.length ? `; the ${photos.length === 1 ? "photo" : `${photos.length} photos`} above go on the item when you save.` : "; photos can be added once it's saved."}
      </p>
      <ItemForm
        key={seed?.n ?? 0}
        defaults={seed?.defaults}
        submitLabel="Save item"
        onCancel={() => navigate(-1)}
        onSubmit={async (payload) => {
          const item = photos.length
            ? await api.createItemFromLibrary(payload, photos.map((p) => ({ sha256: p.sha256, role: p.role })))
            : await api.createItem(payload);
          let note: string | undefined;
          if (seed?.after?.pcgsPriceGuide) {
            try {
              await api.pcgsPriceGuide(item.id);
            } catch (err) {
              note = `Saved, but the PCGS price guide value wasn't: ${(err as Error).message}`;
            }
          }
          await qc.invalidateQueries({ queryKey: ["items"] });
          await qc.invalidateQueries({ queryKey: ["tags"] });
          await qc.invalidateQueries({ queryKey: ["summary"] });
          if (photos.length) {
            await qc.invalidateQueries({ queryKey: ["library"] });
            await qc.invalidateQueries({ queryKey: ["upload-groups"] });
          }
          navigate(`/items/${item.id}`, { replace: true, state: note ? { note } : undefined });
        }}
      />
    </>
  );
}

/** The photos picked on the Photos page: set each one's side, reorder, or leave one out. */
function ChosenPhotos({ photos, onChange, children }: { photos: PickedPhoto[]; onChange: (p: PickedPhoto[]) => void; children?: ReactNode }) {
  const set = (i: number, role: PhotoRole) => onChange(photos.map((p, j) => (j === i ? { ...p, role } : p)));
  const move = (i: number, by: number) => {
    const next = [...photos];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    onChange(next);
  };
  const fronts = photos.filter((p) => p.role === "obverse").length;
  return (
    <section className="panel chosen-photos" aria-labelledby="chosen-h">
      <div className="chosen-head">
        <h2 id="chosen-h">{photos.length === 1 ? "Photo for this item" : `${photos.length} photos for this item`}</h2>
        <Link to="/photos">Choose different photos</Link>
      </div>
      <ol className="chosen-list">
        {photos.map((p, i) => (
          <li key={p.sha256}>
            <img src={p.thumb} alt={p.filename ?? `Photo ${i + 1}`} />
            <label>
              <span className="visually-hidden">Side of photo {i + 1}</span>
              <select value={p.role} onChange={(e) => set(i, e.target.value as PhotoRole)} aria-label={`Side of photo ${i + 1}`}>
                {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <span className="chosen-tools">
              <button type="button" className="ghost small" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move photo ${i + 1} earlier`}>←</button>
              <button type="button" className="ghost small" disabled={i === photos.length - 1} onClick={() => move(i, 1)} aria-label={`Move photo ${i + 1} later`}>→</button>
              <button type="button" className="ghost small" onClick={() => onChange(photos.filter((_, j) => j !== i))} aria-label={`Leave out photo ${i + 1}`}>Leave out</button>
            </span>
          </li>
        ))}
      </ol>
      <p className="hint">
        {fronts > 1 ? "More than one photo is marked as the obverse; the first of them becomes the cover." : fronts === 1 ? "The obverse becomes the cover photo." : "The first photo becomes the cover."}
      </p>
      {children}
    </section>
  );
}
