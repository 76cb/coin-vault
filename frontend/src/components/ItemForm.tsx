import { useQuery } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { api, Composition, CostStatus, Item, ITEM_TYPE_LABELS, ItemStatus, ItemType, Metal, METAL_LABELS, STATUS_LABELS } from "../api";

type Str = string;
interface MetalRow {
  metal: Metal;
  gross_weight_g: Str;
  fineness: Str;
  pure_toz: Str; // empty = computed
  composition_id: Str; // empty = none
}
interface FormState {
  item_type: ItemType;
  title: Str;
  quantity: Str;
  status: ItemStatus;
  location_id: Str;
  acquired_date: Str;
  purchase_price: Str;
  purchase_fees: Str;
  cost_basis_status: CostStatus | "";
  purchase_source: Str;
  notes: Str;
  sale_date: Str;
  sale_price: Str;
  sale_fees: Str;
  sale_venue: Str;
  tags: Str;
  details: Record<string, Str | boolean>;
  grading: "none" | "raw" | "slabbed";
  sheldon_grade: Str;
  grade_text: Str;
  grading_service: Str;
  cert_number: Str;
  designations: Str;
  details_reason: Str;
  metals: MetalRow[];
  valuation_rule: Str;
}

type FieldDef = { key: string; label: string; type?: "number" | "text" | "checkbox" | "select" | "textarea"; options?: string[]; hint?: string };

const COIN_FIELDS: FieldDef[] = [
  { key: "country", label: "Country" },
  { key: "denomination", label: "Denomination" },
  { key: "year", label: "Year", type: "number" },
  { key: "mint_mark", label: "Mint mark" },
  { key: "series", label: "Series" },
  { key: "diameter_mm", label: "Diameter (mm)", type: "number" },
  { key: "numista_id", label: "Numista N#", type: "number" },
  { key: "pcgs_number", label: "PCGS number" },
  { key: "redbook_number", label: "Red Book number" },
  { key: "variety_notes", label: "Variety / die notes", type: "textarea" },
];
const DETAIL_FIELDS: Record<ItemType, FieldDef[]> = {
  coin: COIN_FIELDS,
  bullion: [
    { key: "product_line", label: "Product", hint: "e.g. American Silver Eagle" },
    { key: "mint", label: "Mint or refiner" },
    { key: "country", label: "Country" },
    { key: "year", label: "Year", type: "number" },
    { key: "mint_mark", label: "Mint mark" },
    { key: "numista_id", label: "Numista N#", type: "number" },
  ],
  bar: [
    { key: "weight_value", label: "Weight", type: "number" },
    { key: "weight_unit", label: "Unit", type: "select", options: ["ozt", "g", "kg", "tola"] },
    { key: "refiner", label: "Refiner / mint" },
    { key: "serial_number", label: "Serial number" },
    { key: "has_assay_card", label: "Has assay card", type: "checkbox" },
  ],
  banknote: [
    { key: "country", label: "Country" },
    { key: "denomination", label: "Denomination" },
    { key: "series", label: "Series" },
    { key: "serial_number", label: "Serial number" },
    { key: "pick_number", label: "Pick number" },
  ],
  lot: [
    { key: "face_value", label: "Face value", type: "number" },
    { key: "face_currency", label: "Face currency" },
  ],
  other: [],
};

const DESIGNATION_HINT = "Comma-separated, e.g. CAC, PL, Details";

function s(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

function fromItem(item?: Item, defaults?: Partial<FormState>): FormState {
  const c = item?.condition;
  const details: Record<string, Str | boolean> = {};
  if (item) {
    for (const [k, v] of Object.entries(item.details)) {
      if (k === "attributes") continue;
      details[k] = typeof v === "boolean" ? v : s(v);
    }
    if (item.item_type === "other") {
      const attrs = (item.details.attributes ?? {}) as Record<string, unknown>;
      details.attributes = Object.entries(attrs)
        .map(([k, v]) => (v === "" ? k : `${k}: ${v}`))
        .join("\n");
    }
  }
  return {
    item_type: item?.item_type ?? "coin",
    title: item?.title ?? "",
    quantity: s(item?.quantity ?? 1),
    status: item?.status ?? "owned",
    location_id: s(item?.location_id),
    acquired_date: s(item?.acquired_date),
    purchase_price: s(item?.purchase_price),
    purchase_fees: s(item?.purchase_fees),
    cost_basis_status: item?.cost_basis_status ?? "",
    purchase_source: s(item?.purchase_source),
    notes: s(item?.notes),
    sale_date: s(item?.sale_date),
    sale_price: s(item?.sale_price),
    sale_fees: s(item?.sale_fees),
    sale_venue: s(item?.sale_venue),
    tags: (item?.tags ?? []).join(", "),
    details,
    grading: c ? c.grading : "none",
    sheldon_grade: s(c?.sheldon_grade),
    grade_text: s(c?.grade_text),
    grading_service: s(c?.grading_service),
    cert_number: s(c?.cert_number),
    designations: (c?.designations ?? []).join(", "),
    details_reason: s(c?.details_reason),
    metals: (item?.metal_content ?? []).map((m) => ({
      metal: m.metal,
      gross_weight_g: s(m.gross_weight_g),
      fineness: s(m.fineness),
      pure_toz: m.source === "override" ? s(m.pure_toz) : "",
      composition_id: s(m.composition_id),
      // a reference row shows the reference values as placeholders, not as typed values
      ...(m.source === "reference" ? { gross_weight_g: "", fineness: "" } : {}),
    })),
    valuation_rule: item?.valuation_rule ?? "max",
    ...defaults,
  };
}

const nul = (v: string) => (v.trim() === "" ? null : v.trim());

export function toPayload(f: FormState): Record<string, unknown> {
  const fields = DETAIL_FIELDS[f.item_type];
  const details: Record<string, unknown> = {};
  for (const fd of fields) {
    const v = f.details[fd.key];
    if (fd.type === "checkbox") details[fd.key] = Boolean(v);
    else if (fd.key === "weight_unit") details[fd.key] = v || "ozt";
    else if (fd.key === "face_currency") details[fd.key] = (v as string)?.trim() || "USD";
    else details[fd.key] = nul(String(v ?? ""));
  }
  if (f.item_type === "lot") details.composition_id = f.details.composition_id ? Number(f.details.composition_id) : null;
  if (f.item_type === "other") {
    const attrs: Record<string, string> = {};
    String(f.details.attributes ?? "")
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .forEach((l) => {
        const i = l.indexOf(":");
        if (i > 0) attrs[l.slice(0, i).trim()] = l.slice(i + 1).trim();
        else attrs[l] = "";
      });
    details.attributes = attrs;
  }
  const condition =
    f.grading === "none"
      ? null
      : {
          grading: f.grading,
          sheldon_grade: f.sheldon_grade ? Number(f.sheldon_grade) : null,
          grade_text: nul(f.grade_text),
          grading_service: f.grading === "slabbed" ? nul(f.grading_service) : null,
          cert_number: f.grading === "slabbed" ? nul(f.cert_number) : null,
          designations: f.designations.split(",").map((x) => x.trim()).filter(Boolean),
          details_reason: nul(f.details_reason),
        };
  return {
    item_type: f.item_type,
    title: f.title.trim(),
    quantity: Number(f.quantity) || 1,
    status: f.status,
    location_id: f.location_id ? Number(f.location_id) : null,
    acquired_date: nul(f.acquired_date),
    purchase_price: nul(f.purchase_price),
    purchase_fees: nul(f.purchase_fees),
    ...(f.cost_basis_status ? { cost_basis_status: f.cost_basis_status } : {}),
    purchase_source: nul(f.purchase_source),
    notes: nul(f.notes),
    sale_date: nul(f.sale_date),
    sale_price: nul(f.sale_price),
    sale_fees: nul(f.sale_fees),
    sale_venue: nul(f.sale_venue),
    tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
    details,
    condition,
    metal_content: f.metals.map((m) => ({
      metal: m.metal,
      gross_weight_g: nul(m.gross_weight_g),
      fineness: nul(m.fineness),
      pure_toz: nul(m.pure_toz),
      composition_id: m.composition_id ? Number(m.composition_id) : null,
    })),
    valuation_rule: f.valuation_rule || "max",
  };
}

function fmtToz(v: string | number): string {
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function previewPure(m: MetalRow, comp?: Composition): string {
  if (m.pure_toz) return `${m.pure_toz} ozt (your override)`;
  if (comp && !m.gross_weight_g && !m.fineness) return `${fmtToz(comp.pure_toz)} ozt pure, from the reference: ${comp.label}`;
  const g = Number(m.gross_weight_g);
  const f = Number(m.fineness);
  if (!m.gross_weight_g || !m.fineness || !g || !f) return "";
  return `≈ ${((g / 31.1034768) * f).toFixed(4)} ozt pure`;
}

export default function ItemForm({
  item,
  defaults,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  item?: Item;
  defaults?: Partial<FormState>;
  submitLabel: string;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
  onCancel?: () => void;
}) {
  const [f, setF] = useState<FormState>(() => fromItem(item, defaults));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const locations = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const fields = DETAIL_FIELDS[f.item_type];
  const comps = useQuery({ queryKey: ["compositions"], queryFn: () => api.compositions(), staleTime: 5 * 60_000 });
  const compById = useMemo(() => new Map((comps.data ?? []).map((c) => [String(c.id), c])), [comps.data]);
  const matchParams = useMemo(() => {
    if (f.item_type !== "coin" && f.item_type !== "bullion") return null;
    const p: Record<string, string> = {};
    for (const k of ["country", "denomination", "year", "mint_mark", "series"]) {
      const v = String(f.details[k] ?? "").trim();
      if (v) p[k] = v;
    }
    if (f.item_type === "bullion" && f.details.product_line) p.series = String(f.details.product_line);
    if (!p.denomination && !p.series) return null;
    // Words in the title ("Morgan", "Walking Liberty") help tell apart coins of the same denomination and year.
    if (f.title.trim()) p.series = [p.series, f.title.trim()].filter(Boolean).join(" ");
    return p;
  }, [f.item_type, f.details, f.title]);
  const matches = useQuery({
    queryKey: ["composition-match", matchParams],
    queryFn: () => api.matchCompositions(matchParams!),
    enabled: matchParams !== null,
    staleTime: 60_000,
  });
  // Every match sharing the top score: when the details fit several equally, offer them all rather than guess.
  // Nothing is offered once one of them is in use.
  const top = matches.data?.length ? matches.data.filter((c) => c.score === matches.data![0].score) : [];
  const suggestions = top.some((c) => f.metals.some((m) => m.composition_id === String(c.id))) ? [] : top.slice(0, 3);
  const applyComposition = (c: Composition) =>
    setF((p) => {
      const blank = { gross_weight_g: "", fineness: "", pure_toz: "", composition_id: String(c.id), metal: c.metal };
      const i = p.metals.findIndex((m) => m.metal === c.metal);
      const metals = i >= 0 ? p.metals.map((m, j) => (j === i ? blank : m)) : [...p.metals, blank];
      return { ...p, metals };
    });

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((p) => ({ ...p, [k]: v }));
  const setDetail = (k: string, v: string | boolean) => setF((p) => ({ ...p, details: { ...p.details, [k]: v } }));
  const setMetal = (i: number, patch: Partial<MetalRow>) =>
    setF((p) => ({ ...p, metals: p.metals.map((m, j) => (j === i ? { ...m, ...patch } : m)) }));

  const costHint = useMemo(() => {
    if (!f.purchase_price) return "Leave blank if you don't know what you paid.";
    return "";
  }, [f.purchase_price]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit(toPayload(f));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="item-form" onSubmit={submit} noValidate>
      <fieldset>
        <legend>What it is</legend>
        <div className="grid2">
          <label className="span2">
            Title
            <input value={f.title} onChange={(e) => set("title", e.target.value)} required placeholder="1881-S Morgan Dollar" />
          </label>
          <label>
            Type
            <select value={f.item_type} onChange={(e) => set("item_type", e.target.value as ItemType)}>
              {Object.entries(ITEM_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Quantity
            <input type="number" min={1} inputMode="numeric" value={f.quantity} onChange={(e) => set("quantity", e.target.value)} />
          </label>
          {fields.map((fd) => (
            <DetailInput key={fd.key} def={fd} value={f.details[fd.key]} onChange={(v) => setDetail(fd.key, v)} />
          ))}
          {f.item_type === "other" && (
            <label className="span2">
              Attributes
              <textarea rows={3} value={String(f.details.attributes ?? "")} onChange={(e) => setDetail("attributes", e.target.value)} placeholder={"karat: 14k\nstamp: 585"} />
              <span className="hint">One per line, as name: value.</span>
            </label>
          )}
        </div>
      </fieldset>

      <fieldset>
        <legend>Metal content (per piece)</legend>
        {f.metals.length === 0 && f.item_type !== "lot" && <p className="muted">Add the metal so melt value can be worked out from spot price.</p>}
        {f.item_type === "lot" && (
          <label className="lot-comp">
            Content per {String(f.details.face_currency || "USD")} 1 of face value
            <select value={String(f.details.composition_id ?? "")} onChange={(e) => setDetail("composition_id", e.target.value)}>
              <option value="">Not set</option>
              {comps.data?.filter((c) => c.per_face_unit).map((c) => (
                <option key={c.id} value={c.id}>{c.label} ({fmtToz(c.pure_toz)} ozt per 1)</option>
              ))}
            </select>
            <span className="hint">
              {lotPreview(f, compById) ?? "Pick the kind of junk silver or gold and the face value above; melt value follows from it. Rows below override it."}
            </span>
          </label>
        )}
        {suggestions.length > 0 && (
          <div className="suggest" role="status">
            <p>{suggestions.length === 1 ? "Looks like:" : "From the details so far, it could be any of these:"}</p>
            <ul>
              {suggestions.map((c) => (
                <li key={c.id}>
                  <span>
                    <strong>{c.label}</strong>: {fmtToz(c.pure_toz)} ozt {METAL_LABELS[c.metal].toLowerCase()} per piece.
                  </span>
                  <button type="button" className="small" onClick={() => applyComposition(c)}>Use these figures</button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {f.metals.map((m, i) => {
          const comp = compById.get(m.composition_id);
          return (
          <div className="metal-row" key={i}>
            <label className="metal-ref">
              Reference
              <select
                value={m.composition_id}
                onChange={(e) => {
                  const c = compById.get(e.target.value);
                  setMetal(i, c ? { composition_id: e.target.value, metal: c.metal, gross_weight_g: "", fineness: "", pure_toz: "" } : { composition_id: "" });
                }}
              >
                <option value="">None: I'll enter the weights</option>
                {(Object.keys(METAL_LABELS) as Metal[]).map((metal) => (
                  <optgroup key={metal} label={METAL_LABELS[metal]}>
                    {comps.data?.filter((c) => !c.per_face_unit && c.metal === metal).map((c) => (
                      <option key={c.id} value={c.id}>{c.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label>
              Metal
              <select value={m.metal} onChange={(e) => setMetal(i, { metal: e.target.value as Metal })}>
                {Object.entries(METAL_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Gross weight (g)
              <input inputMode="decimal" value={m.gross_weight_g} onChange={(e) => setMetal(i, { gross_weight_g: e.target.value })} placeholder={comp?.gross_weight_g ? fmtToz(comp.gross_weight_g) : f.item_type === "bar" ? "from bar weight" : ""} />
            </label>
            <label>
              Fineness
              <input inputMode="decimal" value={m.fineness} onChange={(e) => setMetal(i, { fineness: e.target.value })} placeholder={comp?.fineness ? String(Number(comp.fineness)) : "0.900"} />
            </label>
            <label>
              Pure ozt override
              <input inputMode="decimal" value={m.pure_toz} onChange={(e) => setMetal(i, { pure_toz: e.target.value })} placeholder="computed" />
            </label>
            <button type="button" className="ghost small" onClick={() => setF((p) => ({ ...p, metals: p.metals.filter((_, j) => j !== i) }))}>
              Remove
            </button>
            <span className="hint metal-preview">{previewPure(m, comp)}</span>
          </div>
          );
        })}
        <button type="button" className="ghost small" onClick={() => setF((p) => ({ ...p, metals: [...p.metals, { metal: "Ag", gross_weight_g: "", fineness: "", pure_toz: "", composition_id: "" }] }))}>
          Add metal
        </button>
      </fieldset>

      <fieldset>
        <legend>Condition</legend>
        <div className="segmented" role="radiogroup" aria-label="Grading">
          {(["none", "raw", "slabbed"] as const).map((g) => (
            <button type="button" key={g} role="radio" aria-checked={f.grading === g} className={f.grading === g ? "on" : ""} onClick={() => set("grading", g)}>
              {g === "none" ? "Not recorded" : g === "raw" ? "Raw" : "Slabbed"}
            </button>
          ))}
        </div>
        {f.grading !== "none" && (
          <div className="grid2">
            {f.grading === "slabbed" && (
              <>
                <label>
                  Grading company
                  <input list="graders" value={f.grading_service} onChange={(e) => set("grading_service", e.target.value)} />
                  <datalist id="graders">
                    <option value="PCGS" /><option value="NGC" /><option value="ANACS" /><option value="ICG" /><option value="CACG" />
                  </datalist>
                </label>
                <label>
                  Cert number
                  <input value={f.cert_number} onChange={(e) => set("cert_number", e.target.value)} />
                </label>
              </>
            )}
            <label>
              Sheldon grade
              <input type="number" min={1} max={70} value={f.sheldon_grade} onChange={(e) => set("sheldon_grade", e.target.value)} placeholder="1–70" />
            </label>
            <label>
              Grade as written
              <input value={f.grade_text} onChange={(e) => set("grade_text", e.target.value)} placeholder={f.grading === "slabbed" ? "MS63" : "VF details, cleaned"} />
            </label>
            <label>
              Designations
              <input value={f.designations} onChange={(e) => set("designations", e.target.value)} />
              <span className="hint">{DESIGNATION_HINT}</span>
            </label>
            <label>
              Details reason
              <input value={f.details_reason} onChange={(e) => set("details_reason", e.target.value)} placeholder="Cleaned, scratched…" />
            </label>
          </div>
        )}
      </fieldset>

      <fieldset>
        <legend>Purchase</legend>
        <div className="grid2">
          <label>
            Price paid (total for all pieces)
            <input inputMode="decimal" value={f.purchase_price} onChange={(e) => set("purchase_price", e.target.value)} />
            {costHint && <span className="hint">{costHint}</span>}
          </label>
          <label>
            Shipping and fees
            <input inputMode="decimal" value={f.purchase_fees} onChange={(e) => set("purchase_fees", e.target.value)} />
          </label>
          <label>
            Cost is
            <select value={f.cost_basis_status} onChange={(e) => set("cost_basis_status", e.target.value as CostStatus | "")}>
              <option value="">Work it out from the price</option>
              <option value="known">Known</option>
              <option value="estimated">Estimated (gift, inherited)</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label>
            Value it at
            <select value={f.valuation_rule} onChange={(e) => set("valuation_rule", e.target.value)}>
              <option value="max">Higher of melt and market (default)</option>
              <option value="melt">Melt value</option>
              <option value="market">Market value</option>
              <option value="cost">What I paid</option>
            </select>
          </label>
          <label>
            Acquired
            <input type="date" value={f.acquired_date} onChange={(e) => set("acquired_date", e.target.value)} />
          </label>
          <label className="span2">
            Bought from
            <input value={f.purchase_source} onChange={(e) => set("purchase_source", e.target.value)} placeholder="Dealer, show, auction house" />
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Where it is and its status</legend>
        <div className="grid2">
          <label>
            Storage location
            <select value={f.location_id} onChange={(e) => set("location_id", e.target.value)}>
              <option value="">Not set</option>
              {locations.data?.map((l) => (
                <option key={l.id} value={l.id}>{l.path}</option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select value={f.status} onChange={(e) => set("status", e.target.value as ItemStatus)}>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          {f.status === "sold" && (
            <>
              <label>
                Sale date
                <input type="date" value={f.sale_date} onChange={(e) => set("sale_date", e.target.value)} />
              </label>
              <label>
                Sale price
                <input inputMode="decimal" value={f.sale_price} onChange={(e) => set("sale_price", e.target.value)} />
              </label>
              <label>
                Selling fees
                <input inputMode="decimal" value={f.sale_fees} onChange={(e) => set("sale_fees", e.target.value)} />
              </label>
              <label>
                Sold on
                <input value={f.sale_venue} onChange={(e) => set("sale_venue", e.target.value)} placeholder="eBay, dealer…" />
              </label>
            </>
          )}
          <label className="span2">
            Tags
            <input value={f.tags} onChange={(e) => set("tags", e.target.value)} placeholder="Key date, toned" />
            <span className="hint">Comma-separated.</span>
          </label>
          <label className="span2">
            Notes
            <textarea rows={3} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
          </label>
        </div>
      </fieldset>

      {error && <p className="error" role="alert">{error}</p>}
      <div className="form-actions">
        <button className="primary" disabled={busy || !f.title.trim()}>{busy ? "Saving…" : submitLabel}</button>
        {onCancel && <button type="button" className="ghost" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}

function lotPreview(f: FormState, compById: Map<string, Composition>): string | null {
  const c = compById.get(String(f.details.composition_id ?? ""));
  const face = Number(f.details.face_value);
  if (!c || !face) return null;
  return `${face.toLocaleString()} face × ${fmtToz(c.pure_toz)} = ${fmtToz(face * Number(c.pure_toz))} ozt ${METAL_LABELS[c.metal].toLowerCase()} pure.`;
}

function DetailInput({ def, value, onChange }: { def: FieldDef; value: string | boolean | undefined; onChange: (v: string | boolean) => void }) {
  if (def.type === "checkbox") {
    return (
      <label className="check">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {def.label}
      </label>
    );
  }
  if (def.type === "select") {
    return (
      <label>
        {def.label}
        <select value={String(value || def.options![0])} onChange={(e) => onChange(e.target.value)}>
          {def.options!.map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      </label>
    );
  }
  if (def.type === "textarea") {
    return (
      <label className="span2">
        {def.label}
        <textarea rows={2} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
      </label>
    );
  }
  return (
    <label>
      {def.label}
      <input
        inputMode={def.type === "number" ? "decimal" : undefined}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        placeholder={def.hint}
      />
    </label>
  );
}
