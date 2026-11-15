import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AiIdentify as Identified, AiPhotoRef, api, Described, ITEM_TYPE_LABELS, ItemType, PhotoRole, PickedPhoto, ROLE_LABELS, UploadGroup, UploadResult } from "../api";
import { AiIdentify, useAiReady } from "../components/Ai";
import DropZone from "../components/DropZone";
import { payloadFromDescription } from "../components/ItemForm";
import ItemPicker from "../components/ItemPicker";
import { DuplicateNote, QualityNote } from "../components/QualityNote";

const RULE_TEXT: Record<UploadGroup["pairing_rule"], string> = {
  pattern: "Paired by file name",
  order: "Paired by upload order",
  single: "Single photo",
  manual: "Arranged by you",
};

export default function Upload() {
  const qc = useQueryClient();
  const groups = useQuery({ queryKey: ["upload-groups"], queryFn: api.uploadGroups });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [done, setDone] = useState<{ id: number; title: string }[]>([]);

  const refresh = () => qc.invalidateQueries({ queryKey: ["upload-groups"] });
  const ai = useAiReady();
  // Identify all: each group is scanned in turn (one at a time, so the AI server isn't swamped)
  const [scans, setScans] = useState<Record<number, Identified>>({});
  const [scanning, setScanning] = useState<{ done: number; total: number } | null>(null);
  const [scanErrors, setScanErrors] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const refsOf = (g: UploadGroup): AiPhotoRef[] => g.files.filter((f) => f.sha256).map((f) => ({ sha256: f.sha256!, role: f.role }));

  async function identifyAll() {
    const todo = (groups.data ?? []).filter((g) => !scans[g.id] && refsOf(g).length > 0);
    setScanErrors([]);
    setScanning({ done: 0, total: todo.length });
    for (const [i, g] of todo.entries()) {
      try {
        const r = await api.aiIdentify(refsOf(g));
        setScans((s) => ({ ...s, [g.id]: r }));
      } catch (err) {
        setScanErrors((e) => [...e, `${g.files[0]?.original_filename ?? `Group ${g.id}`}: ${(err as Error).message}`]);
      }
      setScanning({ done: i + 1, total: todo.length });
    }
    setScanning(null);
  }

  async function createAll() {
    const ready = (groups.data ?? []).filter((g) => scans[g.id]);
    setCreating(true);
    setError(null);
    try {
      for (const g of ready) {
        const d = scans[g.id].described;
        const item = await api.createItemFromGroup(g.id, payloadFromDescription(d, d.title));
        setDone((x) => [{ id: item.id, title: item.title }, ...x].slice(0, 12));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
      await refresh();
      await qc.invalidateQueries({ queryKey: ["items"] });
    }
  }

  async function upload(files: File[]) {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.bulkUpload(files));
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function merge() {
    try {
      await api.mergeGroups(selected);
      setSelected([]);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const pending = groups.data ?? [];
  const scanned = pending.filter((g) => scans[g.id]).length;

  return (
    <>
      <div className="page-head">
        <h1>Upload photos</h1>
      </div>
      <p className="muted lede">
        Drop a batch from the camera. Files named like <code>0042_obv.jpg</code> and <code>0042_rev.jpg</code> are paired by name; anything else is paired in upload order. Check each group, then save it as a new item or add it to one you already have.
      </p>
      <DropZone label="Upload a batch" onFiles={upload} disabled={busy} />
      {error && <p className="error" role="alert">{error}</p>}
      {result && result.rejected.length > 0 && (
        <div className="notice" role="status">
          <p>{result.rejected.length} file{result.rejected.length > 1 ? "s were" : " was"} not uploaded:</p>
          <ul>{result.rejected.map((r) => <li key={r.filename}><strong>{r.filename}</strong>: {r.reason}</li>)}</ul>
        </div>
      )}
      {done.length > 0 && (
        <p className="success" role="status">
          Saved: {done.map((d, i) => <span key={d.id}>{i > 0 && ", "}<Link to={`/items/${d.id}`}>{d.title}</Link></span>)}
        </p>
      )}

      {pending.length > 0 && (
        <div className="group-toolbar">
          <span className="muted">{pending.length} group{pending.length > 1 ? "s" : ""} waiting</span>
          <button className="ghost small" disabled={selected.length < 2} onClick={merge}>
            Merge {selected.length >= 2 ? selected.length : ""} selected
          </button>
          {ai && (
            <button className="small" disabled={scanning !== null || creating || scanned === pending.length} onClick={identifyAll}>
              {scanning ? `Identifying ${Math.min(scanning.done + 1, scanning.total)} of ${scanning.total}…` : scanned ? `Identify the other ${pending.length - scanned}` : `Identify all ${pending.length}`}
            </button>
          )}
          {scanned > 0 && (
            <button className="primary small" disabled={scanning !== null || creating} onClick={createAll}>
              {creating ? "Creating…" : `Create ${scanned} ${scanned === 1 ? "item" : "items"} as read`}
            </button>
          )}
        </div>
      )}
      {scanned > 0 && !scanning && (
        <p className="hint" role="status">
          {scanned} identified. Check each below (or change a title), then create them one by one, or all at once as the scan read them.
        </p>
      )}
      {scanErrors.length > 0 && (
        <div className="notice" role="status">
          <p>{scanErrors.length} couldn't be identified:</p>
          <ul>{scanErrors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      {groups.data && pending.length === 0 && !busy && <p className="empty">Nothing waiting. Uploaded photos appear here until you save or discard them.</p>}

      <ul className="group-list">
        {pending.map((g) => (
          <GroupCard
            key={g.id}
            group={g}
            preset={scans[g.id] ?? null}
            selected={selected.includes(g.id)}
            onSelect={(on) => setSelected((s) => (on ? [...s, g.id] : s.filter((x) => x !== g.id)))}
            onChanged={refresh}
            onSaved={(id, title) => setDone((d) => [{ id, title }, ...d].slice(0, 6))}
          />
        ))}
      </ul>
    </>
  );
}

function GroupCard({
  group,
  preset,
  selected,
  onSelect,
  onChanged,
  onSaved,
}: {
  group: UploadGroup;
  preset: Identified | null; // what Identify all read for this group
  selected: boolean;
  onSelect: (on: boolean) => void;
  onChanged: () => Promise<unknown>;
  onSaved: (id: number, title: string) => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const ai = useAiReady();
  const [title, setTitle] = useState(group.pairing_rule === "pattern" || group.pairing_rule === "manual" ? group.label ?? "" : "");
  const [type, setType] = useState<ItemType>("coin");
  const [scan, setScan] = useState<Described | null>(null); // what the photo AI read, once "Use this" is pressed
  const [mode, setMode] = useState<"new" | "existing">("new");
  // Identify all fills the title in, as if "Use this" had been pressed (a title already typed is kept)
  useEffect(() => {
    if (!preset) return;
    setScan(preset.described);
    setType(preset.described.item_type);
    setTitle((t) => (t.trim() && t !== (group.label ?? "") ? t : preset.described.title));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const setRole = (fileId: number, role: PhotoRole) => run(() => api.patchGroup(group.id, { roles: { [fileId]: role } }));
  const withSha = group.files.filter((f) => f.sha256);
  const refs: AiPhotoRef[] = withSha.map((f) => ({ sha256: f.sha256!, role: f.role }));
  const picked: PickedPhoto[] = withSha.map((f) => ({ sha256: f.sha256!, thumb: f.urls.thumb, filename: f.original_filename, role: f.role }));

  return (
    <li className={`group-card${selected ? " selected" : ""}`}>
      <div className="group-head">
        <label className="check">
          <input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} />
          <span className="hint">{RULE_TEXT[group.pairing_rule]}</span>
        </label>
        <div className="group-tools">
          {group.files.length > 1 && <button className="ghost small" disabled={busy} onClick={() => run(() => api.splitGroup(group.id))}>Split</button>}
          <button className="ghost small" disabled={busy} onClick={() => run(() => api.discardGroup(group.id))}>Discard</button>
        </div>
      </div>
      <div className="group-files">
        {group.files.map((f) => (
          <figure key={f.id}>
            <div className="flip flip-sm"><div className="flip-window"><img src={f.urls.thumb} alt={f.original_filename} /></div></div>
            <figcaption>
              <select aria-label={`Role for ${f.original_filename}`} value={f.role} disabled={busy} onChange={(e) => setRole(f.id, e.target.value as PhotoRole)}>
                {Object.entries(ROLE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <span className="hint filename">{f.original_filename}</span>
              <QualityNote quality={f.quality} />
              <DuplicateNote kind={f.duplicate_kind} itemId={f.duplicate_of_item_id} />
            </figcaption>
          </figure>
        ))}
      </div>
      {ai && mode === "new" && refs.length > 0 && (
        <AiIdentify
          key={refs.map((r) => r.sha256 + r.role).join()}
          photos={refs}
          preset={preset}
          extra={(r) => (
            <div className="ai-actions">
              <button type="button" className="primary" onClick={() => { setTitle(r.described.title); setType(r.described.item_type); setScan(r.described); }}>Use this</button>
              <button type="button" onClick={() => navigate("/items/new", { state: { photos: picked, described: r.described } })}>Check the details first</button>
            </div>
          )}
        />
      )}
      <div className="group-save">
        <div className="segmented" role="radiogroup" aria-label="Save as">
          <button type="button" role="radio" aria-checked={mode === "new"} className={mode === "new" ? "on" : ""} onClick={() => setMode("new")}>New item</button>
          <button type="button" role="radio" aria-checked={mode === "existing"} className={mode === "existing" ? "on" : ""} onClick={() => setMode("existing")}>Add to existing</button>
        </div>
        {mode === "new" ? (
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              run(async () => {
                // everything the scan read goes with it (details, grade, metal), unless the type was changed since
                const body = scan && scan.item_type === type ? payloadFromDescription(scan, title.trim()) : { item_type: type, title: title.trim() };
                const item = await api.createItemFromGroup(group.id, body);
                onSaved(item.id, item.title);
                await qc.invalidateQueries({ queryKey: ["items"] });
              });
            }}
          >
            <input aria-label="Title" placeholder="Title, e.g. 1921 Peace Dollar" value={title} onChange={(e) => setTitle(e.target.value)} required />
            <select aria-label="Type" value={type} onChange={(e) => setType(e.target.value as ItemType)}>
              {Object.entries(ITEM_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <button className="primary" disabled={busy || !title.trim()}>Create item</button>
            {scan && scan.item_type === type && (
              <span className="hint scan-note">Saves what the scan read: {scanSummary(scan)}. You can edit it afterwards.</span>
            )}
          </form>
        ) : (
          <ItemPicker
            disabled={busy}
            onPick={(it) =>
              run(async () => {
                await api.attachGroup(group.id, it.id);
                onSaved(it.id, it.title);
                await qc.invalidateQueries({ queryKey: ["item", it.id] });
              })
            }
          />
        )}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </li>
  );
}

/** "details, grade, 1 ozt silver" for the note under Create item. */
function scanSummary(d: Described): string {
  const parts = ["details"];
  if (d.condition) parts.push("grade");
  const comp = d.compositions.length && d.compositions.filter((c) => c.score === d.compositions[0].score).length === 1 ? d.compositions[0] : null;
  if (Array.isArray(d.details.coins) && d.details.coins.length) parts.push(`${d.details.coins.length} coins`);
  else if (comp) parts.push(`metal (${comp.label})`);
  else if (d.stamped?.fineness) parts.push(d.stamped.fineness_assumed ? "metal (fineness assumed .999: check it)" : "metal");
  else parts.push("no metal: add it on the item");
  return parts.join(", ");
}
