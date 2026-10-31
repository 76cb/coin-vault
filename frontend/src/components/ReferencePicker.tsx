import { KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { Composition, METAL_LABELS } from "../api";

const fmt = (v: string) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 });

function group(c: Composition): string {
  const kind = c.denomination === "bar" ? "bars" : "coins";
  return `${METAL_LABELS[c.metal]} ${kind}`;
}

/** Type-to-search over the reference list (coins and bars), grouped by metal. */
export default function ReferencePicker({
  options,
  value,
  onChange,
  label = "Reference",
}: {
  options: Composition[];
  value: string;
  onChange: (id: string) => void;
  label?: string;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => String(o.id) === value);

  const results = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const hits = options.filter((o) => {
      const hay = `${o.label} ${o.country ?? ""} ${METAL_LABELS[o.metal]} ${o.denomination ?? ""}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
    const metalOrder = ["Au", "Ag", "Pt", "Pd"];
    hits.sort(
      (a, b) =>
        metalOrder.indexOf(a.metal) - metalOrder.indexOf(b.metal) ||
        Number(a.denomination === "bar") - Number(b.denomination === "bar") ||
        a.label.localeCompare(b.label, undefined, { numeric: true }),
    );
    return hits.slice(0, 80);
  }, [options, query]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (c: Composition | null) => {
    onChange(c ? String(c.id) : "");
    setQuery("");
    setOpen(false);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      setOpen(true);
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && open && results[active]) {
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      return;
    } else return;
    e.preventDefault();
  };

  let lastGroup = "";
  return (
    <div className="refpick" ref={wrap}>
      <label htmlFor={id}>{label}</label>
      {selected && !open ? (
        <div className="refpick-chosen">
          <span>
            {selected.label}
            <span className="hint"> {fmt(selected.pure_toz)} ozt {METAL_LABELS[selected.metal].toLowerCase()}</span>
          </span>
          <button type="button" className="ghost small" onClick={() => { setOpen(true); setTimeout(() => document.getElementById(id)?.focus(), 0); }}>
            Change
          </button>
          <button type="button" className="ghost small" onClick={() => choose(null)}>
            Clear
          </button>
        </div>
      ) : (
        <input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder="Search coins and bars: Valcambi, Maple Leaf, 1 kg…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
        />
      )}
      {open && (
        <ul className="refpick-list" id={`${id}-list`} role="listbox">
          <li role="option" aria-selected={false} className="refpick-none" onMouseDown={(e) => { e.preventDefault(); choose(null); }}>
            None: I'll enter the weights
          </li>
          {results.length === 0 && <li className="refpick-empty">No match. Enter the weight and fineness yourself.</li>}
          {results.map((c, i) => {
            const g = group(c);
            const head = g !== lastGroup ? g : null;
            lastGroup = g;
            return (
              <li key={c.id} role="presentation">
                {head && <div className="refpick-group">{head}</div>}
                <div
                  role="option"
                  aria-selected={i === active}
                  className={`refpick-opt${i === active ? " is-active" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => { e.preventDefault(); choose(c); }}
                >
                  <span>{c.label}</span>
                  <span className="hint tabular">{fmt(c.pure_toz)} ozt</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
