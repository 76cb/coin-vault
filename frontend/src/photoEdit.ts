/**
 * Photo edits, as the server applies them (backend/app/services/photo_edit.py). The editor runs these on
 * its preview so what you see is what gets saved; keep the two in step.
 */

export interface Crop { x: number; y: number; w: number; h: number }

export interface Edits {
  rotate: 0 | 90 | 180 | 270;
  flip: boolean;
  straighten: number; // degrees, clockwise
  crop: Crop | null; // fractions of the straightened frame
  exposure: number;
  contrast: number;
  saturation: number;
  warmth: number;
  sharpness: number;
  circle: boolean; // cut out the circle inside the crop
  background: Background; // outside the circle
}

export type Background = "clear" | "white" | "black";

export const NO_EDITS: Edits = {
  rotate: 0, flip: false, straighten: 0, crop: null, exposure: 0, contrast: 0, saturation: 0, warmth: 0, sharpness: 0,
  circle: false, background: "clear",
};

export const TUNING = ["exposure", "contrast", "saturation", "warmth", "sharpness"] as const;
export type Tuning = (typeof TUNING)[number];

export function fromSaved(saved: Partial<Edits> | null | undefined): Edits {
  return { ...NO_EDITS, ...(saved ?? {}) };
}

const wholeFrame = (c: Crop | null) => !c || (c.x <= 0.0001 && c.y <= 0.0001 && c.w >= 0.9999 && c.h >= 0.9999);

/** Only what differs from no edits; null when nothing does (the server then shows the original). */
export function toSaved(e: Edits): Partial<Edits> | null {
  const out: Partial<Edits> = {};
  if (e.rotate) out.rotate = e.rotate;
  if (e.flip) out.flip = true;
  if (e.straighten) out.straighten = Math.round(e.straighten * 10) / 10;
  if (!wholeFrame(e.crop)) out.crop = roundCrop(e.crop!);
  for (const k of TUNING) if (e[k]) out[k] = Math.round(e[k]);
  if (e.circle) {
    out.circle = true;
    if (e.background !== "clear") out.background = e.background;
  }
  return Object.keys(out).length ? out : null;
}

function roundCrop(c: Crop): Crop {
  const r = (v: number) => Math.round(v * 10000) / 10000;
  const x = Math.max(0, r(c.x));
  const y = Math.max(0, r(c.y));
  return { x, y, w: Math.min(r(c.w), 1 - x), h: Math.min(r(c.h), 1 - y) };
}

export function isEdited(e: Edits): boolean {
  return toSaved(e) !== null;
}

/** How much to enlarge a w x h image turned by `deg` so it still fills a w x h frame. */
export function straightenZoom(w: number, h: number, deg: number): number {
  const a = (Math.abs(deg) * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  return Math.max((w * c + h * s) / w, (w * s + h * c) / h);
}

/** Quarter turns, mirror and straighten applied (no crop, no colour), at most maxEdge on the long side. */
export function frame(src: HTMLImageElement | HTMLCanvasElement, e: Edits, maxEdge: number): HTMLCanvasElement {
  const sw = src instanceof HTMLImageElement ? src.naturalWidth : src.width;
  const sh = src instanceof HTMLImageElement ? src.naturalHeight : src.height;
  const s = Math.min(1, maxEdge / Math.max(sw, sh));
  const w0 = sw * s;
  const h0 = sh * s;
  const quarter = e.rotate === 90 || e.rotate === 270;
  const tw = quarter ? h0 : w0;
  const th = quarter ? w0 : h0;
  const k = straightenZoom(tw, th, e.straighten);
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(tw / k));
  c.height = Math.max(1, Math.round(th / k));
  const ctx = c.getContext("2d")!;
  ctx.imageSmoothingQuality = "high";
  ctx.translate(c.width / 2, c.height / 2);
  ctx.rotate((e.straighten * Math.PI) / 180);
  ctx.scale(e.flip ? -1 : 1, 1);
  ctx.rotate((e.rotate * Math.PI) / 180);
  ctx.drawImage(src, -w0 / 2, -h0 / 2, w0, h0);
  return c;
}

/** The crop of a frame, as a new canvas. */
export function cropped(f: HTMLCanvasElement, crop: Crop | null): HTMLCanvasElement {
  const c = crop ?? { x: 0, y: 0, w: 1, h: 1 };
  const out = document.createElement("canvas");
  out.width = Math.max(1, Math.round(c.w * f.width));
  out.height = Math.max(1, Math.round(c.h * f.height));
  out.getContext("2d")!.drawImage(f, c.x * f.width, c.y * f.height, c.w * f.width, c.h * f.height, 0, 0, out.width, out.height);
  return out;
}

/** Exposure, contrast, saturation, warmth and sharpness, in place. */
export function colour(canvas: HTMLCanvasElement, e: Edits): void {
  if (!TUNING.some((k) => e[k])) return;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = img.data;
  const gain = 2 ** (e.exposure / 100);
  const con = 1 + e.contrast / 100;
  const sat = 1 + e.saturation / 100;
  const wr = 1 + (0.15 * e.warmth) / 100;
  const wb = 1 - (0.15 * e.warmth) / 100;
  const n = canvas.width * canvas.height;
  const f = new Float32Array(n * 3);
  for (let i = 0, j = 0; i < d.length; i += 4, j += 3) {
    let r = (d[i] / 255) * gain;
    let g = (d[i + 1] / 255) * gain;
    let b = (d[i + 2] / 255) * gain;
    if (e.contrast) {
      r = (r - 0.5) * con + 0.5;
      g = (g - 0.5) * con + 0.5;
      b = (b - 0.5) * con + 0.5;
    }
    if (e.saturation) {
      const grey = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      r = grey + (r - grey) * sat;
      g = grey + (g - grey) * sat;
      b = grey + (b - grey) * sat;
    }
    if (e.warmth) {
      r *= wr;
      b *= wb;
    }
    f[j] = r;
    f[j + 1] = g;
    f[j + 2] = b;
  }
  if (e.sharpness) sharpen(f, canvas.width, canvas.height, (1.5 * e.sharpness) / 100);
  for (let i = 0, j = 0; i < d.length; i += 4, j += 3) {
    d[i] = clamp255(f[j]);
    d[i + 1] = clamp255(f[j + 1]);
    d[i + 2] = clamp255(f[j + 2]);
  }
  ctx.putImageData(img, 0, 0);
}

const clamp255 = (v: number) => (v <= 0 ? 0 : v >= 1 ? 255 : Math.round(v * 255));

/** v += amount * (v - 3x3 box blur of v), edges repeated, on values clipped to 0..1 first. */
function sharpen(f: Float32Array, w: number, h: number, amount: number) {
  for (let i = 0; i < f.length; i++) f[i] = Math.min(1, Math.max(0, f[i]));
  const src = f.slice();
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      for (let ch = 0; ch < 3; ch++) {
        let sum = 0;
        for (let dy = -1; dy <= 1; dy++) {
          const yy = Math.min(h - 1, Math.max(0, y + dy));
          for (let dx = -1; dx <= 1; dx++) {
            const xx = Math.min(w - 1, Math.max(0, x + dx));
            sum += src[(yy * w + xx) * 3 + ch];
          }
        }
        const i = (y * w + x) * 3 + ch;
        f[i] = src[i] + amount * (src[i] - sum / 9);
      }
    }
  }
}

/** The circle inside the canvas kept; outside it clear, white or black (the edge is anti-aliased). */
export function circleCut(canvas: HTMLCanvasElement, e: Edits): HTMLCanvasElement {
  if (!e.circle) return canvas;
  const out = document.createElement("canvas");
  out.width = canvas.width;
  out.height = canvas.height;
  const ctx = out.getContext("2d")!;
  if (e.background !== "clear") {
    ctx.fillStyle = e.background === "white" ? "#fff" : "#000";
    ctx.fillRect(0, 0, out.width, out.height);
  }
  ctx.beginPath();
  ctx.ellipse(out.width / 2, out.height / 2, out.width / 2, out.height / 2, 0, 0, Math.PI * 2);
  ctx.clip();
  ctx.drawImage(canvas, 0, 0);
  return out;
}

/** The largest crop of the given shape (width / height in pixels), centred in a fw x fh frame. */
export function centredCrop(fw: number, fh: number, ratio: number | null): Crop | null {
  if (!ratio) return null;
  if (fw / fh > ratio) {
    const w = (ratio * fh) / fw;
    return { x: (1 - w) / 2, y: 0, w, h: 1 };
  }
  const h = fw / (fh * ratio);
  return { x: 0, y: (1 - h) / 2, w: 1, h };
}
