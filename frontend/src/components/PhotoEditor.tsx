import { KeyboardEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { api, Photo, ROLE_LABELS } from "../api";
import { Background, centredCrop, circleCut, colour, Corners, Crop, cropped, Edits, frame, fromSaved, isConvex, isEdited, NO_EDITS, toSaved, Tuning, warp } from "../photoEdit";

const PREVIEW_EDGE = 1100;
const MIN = 0.04; // smallest crop side, as a fraction of the frame

type Shape = "free" | "circle" | "square" | "4:3" | "3:4" | "3:2" | "original";
const SHAPES: { key: Shape; label: string; ratio: (fw: number, fh: number) => number | null }[] = [
  { key: "free", label: "Free", ratio: () => null },
  { key: "circle", label: "Circle", ratio: () => 1 },
  { key: "square", label: "Square", ratio: () => 1 },
  { key: "4:3", label: "4:3", ratio: () => 4 / 3 },
  { key: "3:4", label: "3:4", ratio: () => 3 / 4 },
  { key: "3:2", label: "3:2", ratio: () => 3 / 2 },
  { key: "original", label: "Original", ratio: (fw, fh) => fw / fh },
];

const SLIDERS: { key: Tuning; label: string; min: number }[] = [
  { key: "exposure", label: "Brightness", min: -100 },
  { key: "contrast", label: "Contrast", min: -100 },
  { key: "saturation", label: "Saturation", min: -100 },
  { key: "warmth", label: "Warmth", min: -100 },
  { key: "sharpness", label: "Sharpness", min: 0 },
];

type Handle = "move" | "nw" | "ne" | "sw" | "se";

const BACKGROUNDS: [Background, string][] = [["clear", "Clear"], ["white", "White"], ["black", "Black"]];
const START_CORNERS: Corners = [[0.12, 0.12], [0.88, 0.12], [0.88, 0.88], [0.12, 0.88]];
const CORNER_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"];

/** Crop, straighten, turn and adjust a photo. The original file is kept; Save stores the settings. */
export default function PhotoEditor({ photo, title, onClose, onSaved }: { photo: Photo; title: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [source, setSource] = useState<HTMLImageElement | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [edits, setEdits] = useState<Edits>(() => fromSaved(photo.edits));
  const [tab, setTab] = useState<"crop" | "adjust">("crop");
  const [shape, setShape] = useState<Shape>(() => (photo.edits?.circle ? "circle" : "free"));
  const [finding, setFinding] = useState<"coin" | "slab" | null>(null);
  const [tilting, setTilting] = useState(false);
  const [tiltBefore, setTiltBefore] = useState<{ perspective: Corners | null; crop: Crop | null } | null>(null);
  const [findNote, setFindNote] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const shown = useRef<HTMLCanvasElement>(null);
  const saved = useMemo(() => fromSaved(photo.edits), [photo.edits]);
  const dirty = JSON.stringify(toSaved(edits)) !== JSON.stringify(toSaved(saved));

  useEffect(() => {
    dialog.current?.showModal();
    const img = new Image();
    img.onload = () => setSource(img);
    img.onerror = () => setLoadError("The photo couldn't be loaded for editing.");
    img.src = photo.urls.unedited ?? photo.urls.medium;
  }, [photo]);

  // the frame: quarter turns, mirror and straighten; recomputed only when those change
  const base = useMemo(
    () => (source ? frame(source, { ...NO_EDITS, rotate: edits.rotate, flip: edits.flip, straighten: edits.straighten }, PREVIEW_EDGE) : null),
    [source, edits.rotate, edits.flip, edits.straighten],
  );
  // then the tilt correction (not while its corners are being placed: that shows the untilted frame)
  const corners = tilting ? null : edits.perspective;
  const geometry = useMemo(() => (base && corners ? warp(base, corners) : base), [base, corners]);

  // draw: the whole frame while cropping, the cropped photo while adjusting; colour on both
  useEffect(() => {
    if (!geometry || !shown.current) return;
    const id = requestAnimationFrame(() => {
      const target = shown.current!;
      let out: HTMLCanvasElement;
      if (comparing && source) {
        out = frame(source, NO_EDITS, PREVIEW_EDGE);
      } else if (tilting && base) {
        out = cropped(base, null);
        colour(out, edits);
      } else {
        out = tab === "adjust" ? cropped(geometry, edits.crop) : cropped(geometry, null);
        colour(out, edits);
        if (tab === "adjust") out = circleCut(out, edits);
      }
      // a small crop is shown enlarged while adjusting, so its detail can be judged
      const k = tab === "adjust" && !comparing ? Math.max(1, Math.min(4, 720 / Math.max(out.width, out.height))) : 1;
      target.width = Math.round(out.width * k);
      target.height = Math.round(out.height * k);
      const ctx = target.getContext("2d")!;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(out, 0, 0, target.width, target.height);
    });
    return () => cancelAnimationFrame(id);
  }, [geometry, base, tilting, edits, tab, comparing, source]);

  const fw = geometry?.width ?? 1;
  const fh = geometry?.height ?? 1;
  const ratio = SHAPES.find((s) => s.key === shape)!.ratio(fw, fh);
  const crop = edits.crop ?? { x: 0, y: 0, w: 1, h: 1 };
  const set = (patch: Partial<Edits>) => setEdits((e) => ({ ...e, ...patch }));

  const chooseShape = (s: Shape) => {
    setShape(s);
    setFindNote(null);
    const r = SHAPES.find((x) => x.key === s)!.ratio(fw, fh);
    const keep = s === "circle" && edits.crop && Math.abs(edits.crop.w * fw - edits.crop.h * fh) < 2; // already square: keep it
    set({ crop: keep ? edits.crop : r ? centredCrop(fw, fh, r) : edits.crop, circle: s === "circle" });
  };

  // the server looks for the coin's rim in the frame as turned now, and gives back a square around it
  const findCoin = async () => {
    setFinding("coin");
    setFindNote(null);
    try {
      const { crop: found } = await api.findCoin(photo.id, { rotate: edits.rotate, flip: edits.flip, straighten: edits.straighten, perspective: edits.perspective });
      if (shape !== "circle" && shape !== "square") setShape("circle");
      set({ crop: found, circle: shape === "square" ? edits.circle : true });
      setFindNote("Found it. Drag the circle if it's not quite right.");
    } catch (err) {
      setFindNote((err as Error).message);
    } finally {
      setFinding(null);
    }
  };

  // ...and for a holder's four corners, which become the tilt correction: the slab, squared up, fills the frame
  const findSlab = async () => {
    setFinding("slab");
    setFindNote(null);
    try {
      const { perspective } = await api.findSlab(photo.id, { rotate: edits.rotate, flip: edits.flip, straighten: edits.straighten });
      setTilting(false);
      setShape("free");
      set({ perspective, crop: null, circle: false });
      setFindNote("Found the holder and squared it up. If a corner's off, use Adjust tilt and drag it.");
    } catch (err) {
      setFindNote((err as Error).message);
    } finally {
      setFinding(null);
    }
  };

  const startTilt = () => {
    setTiltBefore({ perspective: edits.perspective, crop: edits.crop });
    setTilting(true);
    setFindNote(null);
    if (!edits.perspective) set({ perspective: START_CORNERS });
  };
  const endTilt = (keep: boolean) => {
    if (!keep && tiltBefore) set(tiltBefore);
    else if (keep) {
      set({ crop: null, circle: false }); // the frame is a new shape: the crop starts again
      setShape("free");
    }
    setTilting(false);
    setTiltBefore(null);
  };
  const turn = (by: 90 | -90) => {
    const rotate = (((edits.rotate + by) % 360) + 360) % 360 as Edits["rotate"];
    // the frame's shape changes, so the crop starts again (in the chosen shape)
    const [bw, bh] = [base?.width ?? fw, base?.height ?? fh];
    const [nw, nh] = rotate % 180 === edits.rotate % 180 ? [bw, bh] : [bh, bw];
    // tilt corners belong to the frame as it was turned, so they go too
    set({ rotate, perspective: null, crop: ratio && shape !== "original" ? centredCrop(nw, nh, ratio) : null });
  };

  // --- crop box dragging -----------------------------------------------------
  const drag = useRef<{ handle: Handle; start: Crop; px: number; py: number; rect: DOMRect } | null>(null);

  const onDown = (handle: Handle) => (ev: PointerEvent) => {
    ev.preventDefault();
    ev.stopPropagation();
    const rect = shown.current!.getBoundingClientRect();
    drag.current = { handle, start: crop, px: ev.clientX, py: ev.clientY, rect };
    (ev.target as Element).setPointerCapture(ev.pointerId);
    setDragging(true);
  };

  const cornerDrag = useRef<{ i: number; start: Corners; px: number; py: number; rect: DOMRect } | null>(null);
  const onCornerDown = (i: number) => (ev: PointerEvent) => {
    ev.preventDefault();
    ev.stopPropagation();
    cornerDrag.current = { i, start: edits.perspective ?? START_CORNERS, px: ev.clientX, py: ev.clientY, rect: shown.current!.getBoundingClientRect() };
    (ev.target as Element).setPointerCapture(ev.pointerId);
    setDragging(true);
  };
  const moveCorner = (start: Corners, i: number, dx: number, dy: number) => {
    const next = start.map((p) => [...p]) as Corners;
    next[i] = [clamp(start[i][0] + dx, 0, 1), clamp(start[i][1] + dy, 0, 1)];
    if (isConvex(next)) set({ perspective: next }); // a crossed or dented shape can't be a rectangle
  };
  const onCornerKey = (i: number) => (ev: KeyboardEvent) => {
    const step = ev.altKey ? 0.002 : 0.01;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const m = moves[ev.key];
    if (!m) return;
    ev.preventDefault();
    moveCorner(edits.perspective ?? START_CORNERS, i, m[0], m[1]);
  };

  const onMove = (ev: PointerEvent) => {
    const cd = cornerDrag.current;
    if (cd) {
      moveCorner(cd.start, cd.i, (ev.clientX - cd.px) / cd.rect.width, (ev.clientY - cd.py) / cd.rect.height);
      return;
    }
    const d = drag.current;
    if (!d) return;
    const dx = (ev.clientX - d.px) / d.rect.width;
    const dy = (ev.clientY - d.py) / d.rect.height;
    const s = d.start;
    if (d.handle === "move") {
      set({ crop: { ...s, x: clamp(s.x + dx, 0, 1 - s.w), y: clamp(s.y + dy, 0, 1 - s.h) } });
      return;
    }
    const west = d.handle.includes("w");
    const north = d.handle.includes("n");
    const ax = west ? s.x + s.w : s.x; // the corner that stays put
    const ay = north ? s.y + s.h : s.y;
    const px = (west ? s.x : s.x + s.w) + dx;
    const py = (north ? s.y : s.y + s.h) + dy;
    let w = clamp(west ? ax - px : px - ax, MIN, west ? ax : 1 - ax);
    let h = clamp(north ? ay - py : py - ay, MIN, north ? ay : 1 - ay);
    if (ratio) {
      // h in frame fractions for this w at the chosen shape; shrink whichever side overflows
      const hFor = (ww: number) => (ww * fw) / (fh * ratio);
      const wFor = (hh: number) => (hh * fh * ratio) / fw;
      if (Math.abs(dx) * fw >= Math.abs(dy) * fh) h = hFor(w);
      else w = wFor(h);
      const maxH = north ? ay : 1 - ay;
      const maxW = west ? ax : 1 - ax;
      if (h > maxH) { h = maxH; w = wFor(h); }
      if (w > maxW) { w = maxW; h = hFor(w); }
    }
    set({ crop: { x: west ? ax - w : ax, y: north ? ay - h : ay, w, h } });
  };

  const onUp = () => {
    drag.current = null;
    cornerDrag.current = null;
    setDragging(false);
  };

  const onBoxKey = (ev: KeyboardEvent) => {
    const step = ev.altKey ? 0.002 : 0.01;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const m = moves[ev.key];
    if (!m) return;
    ev.preventDefault();
    if (ev.shiftKey && !ratio) {
      set({ crop: { ...crop, w: clamp(crop.w + m[0], MIN, 1 - crop.x), h: clamp(crop.h + m[1], MIN, 1 - crop.y) } });
    } else {
      set({ crop: { ...crop, x: clamp(crop.x + m[0], 0, 1 - crop.w), y: clamp(crop.y + m[1], 0, 1 - crop.h) } });
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.setPhotoEdits(photo.id, toSaved(edits));
      await onSaved();
      close();
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  };

  const close = () => {
    dialog.current?.close();
    onClose();
  };

  const pct = (v: number) => `${v * 100}%`;
  const cropW = Math.round(crop.w * fw * (photo.width / Math.max(1, fw)));

  return (
    <dialog
      ref={dialog}
      className="photo-editor"
      aria-label={`Edit ${ROLE_LABELS[photo.role].toLowerCase()} photo of ${title}`}
      onCancel={(e) => { e.preventDefault(); if (!dirty || window.confirm("Discard your changes to this photo?")) close(); }}
    >
      <div className="pe-stage" onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
        {loadError ? (
          <p className="error">{loadError}</p>
        ) : !source ? (
          <p className="pe-loading">Loading photo…</p>
        ) : (
          <div className="pe-canvas-wrap">
            <canvas ref={shown} className="pe-canvas" />
            {tab === "crop" && !comparing && tilting && edits.perspective && (
              <div className="pe-crop-layer pe-tilt-layer">
                <svg className="pe-tilt-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
                  <path
                    fillRule="evenodd"
                    className="pe-tilt-shade"
                    d={`M0 0H100V100H0Z M${edits.perspective.map(([x, y]) => `${x * 100} ${y * 100}`).join(" L")}Z`}
                  />
                  <polygon className="pe-tilt-edge" points={edits.perspective.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")} vectorEffect="non-scaling-stroke" />
                </svg>
                {edits.perspective.map(([x, y], i) => (
                  <span
                    key={i}
                    className="pe-corner"
                    style={{ left: pct(x), top: pct(y) }}
                    onPointerDown={onCornerDown(i)}
                    onKeyDown={onCornerKey(i)}
                    tabIndex={0}
                    role="slider"
                    aria-label={`${CORNER_NAMES[i]} corner. Arrow keys move it.`}
                    aria-valuetext={`${Math.round(x * 100)}% across, ${Math.round(y * 100)}% down`}
                  />
                ))}
              </div>
            )}
            {tab === "crop" && !comparing && !tilting && (
              <div className="pe-crop-layer">
                {edits.circle && (
                  <div className="pe-cut-shade" aria-hidden>
                    <span style={{ left: pct(crop.x), top: pct(crop.y), width: pct(crop.w), height: pct(crop.h) }} />
                  </div>
                )}
                <div className={`pe-shade${edits.circle ? " is-hidden" : ""}`} style={{ clipPath: `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0, ${pct(crop.x)} ${pct(crop.y)}, ${pct(crop.x)} ${pct(crop.y + crop.h)}, ${pct(crop.x + crop.w)} ${pct(crop.y + crop.h)}, ${pct(crop.x + crop.w)} ${pct(crop.y)}, ${pct(crop.x)} ${pct(crop.y)})` }} />
                <div
                  className={`pe-box${dragging ? " is-dragging" : ""}`}
                  style={{ left: pct(crop.x), top: pct(crop.y), width: pct(crop.w), height: pct(crop.h) }}
                  onPointerDown={onDown("move")}
                  tabIndex={0}
                  role="group"
                  aria-label="Crop area. Arrow keys move it; Shift and arrows resize it."
                  onKeyDown={onBoxKey}
                >
                  {(shape === "square" || shape === "circle" || edits.circle) && <span className={`pe-circle${edits.circle ? " is-cut" : ""}`} aria-hidden />}
                  <span className="pe-thirds" aria-hidden />
                  {(["nw", "ne", "sw", "se"] as Handle[]).map((h) => (
                    <span key={h} className={`pe-handle pe-${h}`} onPointerDown={onDown(h)} aria-hidden />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="pe-panel">
        <div className="pe-head">
          <h2>Edit photo</h2>
          <p className="hint">Your original is kept. You can reset to it at any time.</p>
        </div>
        <div className="segmented pe-tabs" role="tablist" aria-label="Editing tools">
          <button type="button" role="tab" aria-selected={tab === "crop"} className={tab === "crop" ? "on" : ""} onClick={() => setTab("crop")}>Crop and turn</button>
          <button type="button" role="tab" aria-selected={tab === "adjust"} className={tab === "adjust" ? "on" : ""} disabled={tilting} onClick={() => setTab("adjust")}>Adjust</button>
        </div>

        {tab === "crop" ? (
          <div className="pe-tools" role="tabpanel">
            <fieldset className="pe-shapes" hidden={tilting}>
              <legend>Shape</legend>
              {SHAPES.map((s) => (
                <button key={s.key} type="button" className={`chip${shape === s.key ? " on" : ""}`} aria-pressed={shape === s.key} onClick={() => chooseShape(s.key)}>
                  {s.label}
                </button>
              ))}
              {shape === "square" && <p className="hint">The circle helps centre a coin.</p>}
            </fieldset>
            {tilting ? (
              <div className="pe-tilt-tools">
                <p className="hint">
                  Drag each corner onto a corner of the holder (or anything that should be a rectangle). The photo is squared up so they make one.
                </p>
                <div className="pe-turns">
                  <button type="button" className="primary" onClick={() => endTilt(true)}>Done</button>
                  <button type="button" onClick={() => endTilt(false)}>Cancel</button>
                </div>
              </div>
            ) : (
              <div className="pe-find">
                <button type="button" onClick={findCoin} disabled={finding !== null || !source}>{finding === "coin" ? "Looking…" : "Find the coin"}</button>
                <button type="button" onClick={findSlab} disabled={finding !== null || !source}>{finding === "slab" ? "Looking…" : "Find the slab"}</button>
                <button type="button" onClick={startTilt} disabled={!source}>{edits.perspective ? "Adjust tilt" : "Fix tilt"}</button>
                {edits.perspective && <button type="button" className="ghost small" onClick={() => set({ perspective: null, crop: null })}>Remove tilt fix</button>}
                {findNote && <p className="hint" role="status">{findNote}</p>}
              </div>
            )}
            {edits.circle && !tilting && (
              <fieldset className="pe-shapes">
                <legend>Outside the circle</legend>
                {BACKGROUNDS.map(([k, label]) => (
                  <button key={k} type="button" className={`chip${edits.background === k ? " on" : ""}`} aria-pressed={edits.background === k} onClick={() => set({ background: k })}>
                    {label}
                  </button>
                ))}
                <p className="hint">Clear lets the page show through, so the coin sits on any background.</p>
              </fieldset>
            )}
            <div className="pe-turns">
              <button type="button" disabled={tilting} onClick={() => turn(-90)}>Turn left</button>
              <button type="button" disabled={tilting} onClick={() => turn(90)}>Turn right</button>
              <button type="button" aria-pressed={edits.flip} className={edits.flip ? "on" : ""} disabled={tilting} onClick={() => set({ flip: !edits.flip, perspective: null, crop: null })}>Mirror</button>
            </div>
            <Slider label="Straighten" value={edits.straighten} min={-45} max={45} step={0.5} unit="°" onChange={(v) => set({ straighten: v })} />
            <p className="hint tabular">{edits.crop ? `Crop: about ${cropW.toLocaleString()} px wide` : "No crop"}</p>
          </div>
        ) : (
          <div className="pe-tools" role="tabpanel">
            {SLIDERS.map((s) => (
              <Slider key={s.key} label={s.label} value={edits[s.key]} min={s.min} max={100} step={1} onChange={(v) => set({ [s.key]: v } as Partial<Edits>)} />
            ))}
          </div>
        )}

        <div className="pe-compare">
          <button
            type="button"
            className="ghost small"
            disabled={!isEdited(edits)}
            onPointerDown={() => setComparing(true)}
            onPointerUp={() => setComparing(false)}
            onPointerLeave={() => setComparing(false)}
            onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") setComparing(true); }}
            onKeyUp={() => setComparing(false)}
          >
            Hold to see the original
          </button>
          <button type="button" className="ghost small" disabled={!isEdited(edits)} onClick={() => { setEdits(NO_EDITS); setShape("free"); setTilting(false); setTiltBefore(null); }}>
            Reset to original
          </button>
        </div>

        {error && <p className="error" role="alert">{error}</p>}
        <div className="pe-actions">
          <button type="button" onClick={() => { if (!dirty || window.confirm("Discard your changes to this photo?")) close(); }}>Cancel</button>
          <button type="button" className="primary" disabled={!dirty || saving || !source || tilting} onClick={save}>
            {saving ? "Saving…" : "Save photo"}
          </button>
        </div>
      </div>
    </dialog>
  );
}

function Slider({ label, value, min, max, step, unit = "", onChange }: {
  label: string; value: number; min: number; max: number; step: number; unit?: string; onChange: (v: number) => void;
}) {
  const id = `pe-${label.toLowerCase()}`;
  return (
    <div className="pe-slider">
      <label htmlFor={id}>{label}</label>
      <button type="button" className="pe-value tabular" title={`Reset ${label.toLowerCase()}`} aria-label={`Reset ${label.toLowerCase()}, now ${value}${unit}`} disabled={value === 0} onClick={() => onChange(0)}>
        {value > 0 && min < 0 ? "+" : ""}{value}{unit}
      </button>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
