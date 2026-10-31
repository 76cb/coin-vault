import { KeyboardEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";

export interface Point {
  t: number; // epoch ms
  v: number;
}

const H = 240;
const PAD = { top: 16, right: 16, bottom: 28, left: 64 };

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    const d = Math.abs(min) * 0.05 || 1;
    min -= d;
    max += d;
  }
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  const out: number[] = [];
  for (let v = Math.floor(min / step) * step; v <= max + step * 0.001; v += step) out.push(+v.toFixed(10));
  if (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
  return out;
}

/**
 * A line chart with a crosshair tooltip. One axis and one hue; the title names the series.
 * An optional second series (`compare`, the same times) is drawn as a quiet dashed line, with a key.
 */
export default function LineChart({
  points,
  format,
  formatTime,
  formatTip,
  label,
  seriesLabel,
  compare,
}: {
  points: Point[];
  format: (v: number) => string;
  formatTime: (t: number) => string;
  formatTip?: (t: number) => string;
  label: string;
  seriesLabel?: string; // names the main line in the key and tooltip when there's a compare line
  compare?: { points: Point[]; label: string };
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = useMemo(() => {
    const ts = points.map((p) => p.t);
    const vs = [...points, ...(compare?.points ?? [])].map((p) => p.v);
    const t0 = Math.min(...ts);
    const t1 = Math.max(...ts);
    const ticks = niceTicks(Math.min(...vs), Math.max(...vs));
    const y0 = ticks[0];
    const y1 = ticks[ticks.length - 1];
    const iw = width - PAD.left - PAD.right;
    const ih = H - PAD.top - PAD.bottom;
    const x = (t: number) => PAD.left + (t1 === t0 ? iw / 2 : ((t - t0) / (t1 - t0)) * iw);
    const y = (v: number) => PAD.top + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
    const line = points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    const cline = (compare?.points ?? []).map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    const area = `${line}L${x(t1).toFixed(1)},${PAD.top + ih}L${x(t0).toFixed(1)},${PAD.top + ih}Z`;
    const xTickCount = Math.max(2, Math.min(6, Math.floor(iw / 110)));
    const xTicks = Array.from({ length: xTickCount }, (_, i) => t0 + ((t1 - t0) * i) / (xTickCount - 1));
    return { x, y, line, cline, area, ticks, xTicks, ih };
  }, [points, compare, width]);

  const nearest = (clientX: number) => {
    const rect = wrap.current!.getBoundingClientRect();
    const px = clientX - rect.left;
    let best = 0;
    let bestD = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(geo.x(p.t) - px);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best;
  };

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? points.length) - 1));
    else if (e.key === "ArrowRight") setHover((h) => Math.min(points.length - 1, (h ?? -1) + 1));
    else if (e.key === "Escape") setHover(null);
    else return;
    e.preventDefault();
  };

  const last = points[points.length - 1];
  const hp = hover !== null ? points[hover] : null;
  const cp = hover !== null ? compare?.points[hover] : undefined;
  const tipLeft = hp ? Math.min(Math.max(geo.x(hp.t), 70), width - 70) : 0;

  const chart = (
    <div
      ref={wrap}
      className="linechart"
      tabIndex={0}
      role="img"
      aria-label={`${label}. Latest ${format(last.v)} on ${formatTime(last.t)}${compare?.points.length ? `; ${compare.label.toLowerCase()} ${format(compare.points[compare.points.length - 1].v)}` : ""}. Use the arrow keys to read values.`}
      onPointerMove={(e: PointerEvent) => setHover(nearest(e.clientX))}
      onPointerLeave={() => setHover(null)}
      onKeyDown={onKey}
      onBlur={() => setHover(null)}
    >
      <svg width={width} height={H} aria-hidden="true">
        {geo.ticks.map((v) => (
          <g key={v}>
            <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={geo.y(v)} y2={geo.y(v)} />
            <text className="axis" x={PAD.left - 8} y={geo.y(v)} dy="0.32em" textAnchor="end">{format(v)}</text>
          </g>
        ))}
        {geo.xTicks.map((t, i) => (
          <text key={t} className="axis" x={geo.x(t)} y={H - 8} textAnchor={i === 0 ? "start" : i === geo.xTicks.length - 1 ? "end" : "middle"}>
            {formatTime(t)}
          </text>
        ))}
        <path className="area" d={geo.area} />
        {compare && <path className="line compare" d={geo.cline} />}
        <path className="line" d={geo.line} />
        <circle className="end-dot" cx={geo.x(last.t)} cy={geo.y(last.v)} r={4} />
        {hp && (
          <>
            <line className="crosshair" x1={geo.x(hp.t)} x2={geo.x(hp.t)} y1={PAD.top} y2={PAD.top + geo.ih} />
            <circle className="end-dot" cx={geo.x(hp.t)} cy={geo.y(hp.v)} r={5} />
          </>
        )}
      </svg>
      {hp && (
        <div className="chart-tip" style={{ left: tipLeft }} role="status">
          <strong className="tabular">{compare && seriesLabel ? `${seriesLabel} ` : ""}{format(hp.v)}</strong>
          {cp && <span className="tabular">{compare!.label} {format(cp.v)}</span>}
          <span>{(formatTip ?? formatTime)(hp.t)}</span>
        </div>
      )}
    </div>
  );
  if (!compare) return chart;
  return (
    <>
      <ul className="chart-key" aria-hidden="true">
        <li><span className="key-line" />{seriesLabel ?? label}</li>
        <li><span className="key-line compare" />{compare.label}</li>
      </ul>
      {chart}
    </>
  );
}
