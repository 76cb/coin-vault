/**
 * Photo edits, as the server applies them (backend/app/services/photo_edit.py). The editor runs these on
 * its preview so what you see is what gets saved; keep the two in step.
 */

export interface Crop { x: number; y: number; w: number; h: number }
/** Top-left, top-right, bottom-right, bottom-left: fractions of the straightened frame. */
export type Corners = [number, number][];

export interface Edits {
  rotate: 0 | 90 | 180 | 270;
  flip: boolean;
  straighten: number; // degrees, clockwise
  perspective: Corners | null; // tilt correction: these corners become a rectangle
  crop: Crop | null; // fractions of the frame after straighten and tilt
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
  rotate: 0, flip: false, straighten: 0, perspective: null, crop: null, exposure: 0, contrast: 0, saturation: 0, warmth: 0, sharpness: 0,
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
  if (e.perspective) out.perspective = e.perspective.map(([x, y]) => [round4(x), round4(y)]);
  if (!wholeFrame(e.crop)) out.crop = roundCrop(e.crop!);
  for (const k of TUNING) if (e[k]) out[k] = Math.round(e[k]);
  if (e.circle) {
    out.circle = true;
    if (e.background !== "clear") out.background = e.background;
  }
  return Object.keys(out).length ? out : null;
}

const round4 = (v: number) => Math.min(1, Math.max(0, Math.round(v * 10000) / 10000));

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

/** Width and height of the rectangle a quadrilateral (pixels) is straightened into: the longer top or bottom
 *  side, and the longer left or right side (as backend/app/services/slab.py). */
export function straightenedSize(q: [number, number][]): [number, number] {
  const d = (a: [number, number], b: [number, number]) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  return [Math.max(d(q[0], q[1]), d(q[3], q[2])), Math.max(d(q[0], q[3]), d(q[1], q[2]))];
}

/** For each output point (x, y), the input point ((a x + b y + c) / (g x + h y + 1), (d x + e y + f) / (g x + h y + 1)),
 *  with dst[i] going to src[i]: PIL's PERSPECTIVE coefficients. */
export function perspectiveCoeffs(dst: [number, number][], src: [number, number][]): number[] {
  const m: number[][] = [];
  dst.forEach(([x, y], i) => {
    const [u, v] = src[i];
    m.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    m.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  });
  for (let c = 0; c < 8; c++) { // Gaussian elimination with partial pivoting
    let p = c;
    for (let r = c + 1; r < 8; r++) if (Math.abs(m[r][c]) > Math.abs(m[p][c])) p = r;
    [m[c], m[p]] = [m[p], m[c]];
    for (let r = 0; r < 8; r++) {
      if (r === c) continue;
      const f = m[r][c] / m[c][c];
      for (let k = c; k < 9; k++) m[r][k] -= f * m[c][k];
    }
  }
  return m.map((row, i) => row[8] / row[i]);
}

/** The quadrilateral `corners` of a frame straightened into a rectangle (bilinear sampling). */
export function warp(f: HTMLCanvasElement, corners: Corners): HTMLCanvasElement {
  const src = corners.map(([x, y]) => [x * f.width, y * f.height] as [number, number]);
  const [ow, oh] = straightenedSize(src).map((v) => Math.max(1, Math.round(v)));
  const [a, b, c, d, e, g0, g, h] = perspectiveCoeffs([[0, 0], [ow, 0], [ow, oh], [0, oh]], src);
  const sw = f.width;
  const sh = f.height;
  const sd = f.getContext("2d", { willReadFrequently: true })!.getImageData(0, 0, sw, sh).data;
  const out = document.createElement("canvas");
  out.width = ow;
  out.height = oh;
  const octx = out.getContext("2d")!;
  const img = octx.createImageData(ow, oh);
  const od = img.data;
  for (let y = 0; y < oh; y++) {
    const yc = y + 0.5;
    for (let x = 0; x < ow; x++) {
      const xc = x + 0.5;
      const den = g * xc + h * yc + 1;
      const u = (a * xc + b * yc + c) / den - 0.5;
      const v = (d * xc + e * yc + g0) / den - 0.5;
      const o = (y * ow + x) * 4;
      if (u < -0.5 || v < -0.5 || u > sw - 0.5 || v > sh - 0.5) continue; // outside: left clear
      const x0 = Math.max(0, Math.min(sw - 1, Math.floor(u)));
      const y0 = Math.max(0, Math.min(sh - 1, Math.floor(v)));
      const x1 = Math.min(sw - 1, x0 + 1);
      const y1 = Math.min(sh - 1, y0 + 1);
      const fx = Math.max(0, Math.min(1, u - x0));
      const fy = Math.max(0, Math.min(1, v - y0));
      for (let ch = 0; ch < 4; ch++) {
        const p00 = sd[(y0 * sw + x0) * 4 + ch];
        const p10 = sd[(y0 * sw + x1) * 4 + ch];
        const p01 = sd[(y1 * sw + x0) * 4 + ch];
        const p11 = sd[(y1 * sw + x1) * 4 + ch];
        od[o + ch] = (p00 * (1 - fx) + p10 * fx) * (1 - fy) + (p01 * (1 - fx) + p11 * fx) * fy;
      }
    }
  }
  octx.putImageData(img, 0, 0);
  return out;
}

/** True for four corners going round one way (no crossed sides, no dents). */
export function isConvex(q: Corners): boolean {
  const s = q.map((p, i) => {
    const b = q[(i + 1) % 4];
    const c = q[(i + 2) % 4];
    return (b[0] - p[0]) * (c[1] - b[1]) - (b[1] - p[1]) * (c[0] - b[0]);
  });
  return s.every((v) => v > 0) || s.every((v) => v < 0);
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
