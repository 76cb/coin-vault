import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { api, Item, ITEM_TYPE_LABELS, Metal, METAL_LABELS, money, ozt, ROLE_LABELS, RULE_LABELS, STATUS_LABELS } from "../api";
import { AiGradeGuess, AiIdentify, useAiReady } from "../components/Ai";
import Documents from "../components/Documents";
import ItemForm, { fillBlanks, FormState } from "../components/ItemForm";
import MarketValue from "../components/MarketValue";
import PhotoManager from "../components/PhotoManager";

const DETAIL_LABELS: Record<string, string> = {
  country: "Country",
  denomination: "Denomination",
  year: "Year",
  mint_mark: "Mint mark",
  series: "Series",
  product_line: "Product",
  mint: "Mint",
  diameter_mm: "Diameter (mm)",
  composition: "Composition",
  weight_g: "Weight (g)",
  numista_id: "Numista N#",
  numista_issue_id: "Numista issue",
  pcgs_number: "PCGS number",
  redbook_number: "Red Book number",
  variety_notes: "Variety, label or pedigree",
  weight_value: "Weight",
  weight_unit: "Unit",
  refiner: "Refiner",
  serial_number: "Serial number",
  has_assay_card: "Assay card",
  pick_number: "Pick number",
  face_value: "Face value",
  face_currency: "Face currency",
};

function grade(item: Item): string | null {
  const c = item.condition;
  if (!c) return null;
  const parts = [c.grading === "slabbed" ? c.grading_service : "Raw", c.grade_text ?? (c.sheldon_grade ? String(c.sheldon_grade) : null), ...c.designations];
  return parts.filter(Boolean).join(" ");
}

export default function ItemPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const note = (useLocation().state as { note?: string } | null)?.note;
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [editSeed, setEditSeed] = useState<{ n: number; defaults: Partial<FormState> } | null>(null);
  const ai = useAiReady();
  const [showHistory, setShowHistory] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const item = useQuery({ queryKey: ["item", id], queryFn: () => api.item(id) });
  const audit = useQuery({ queryKey: ["audit", id], queryFn: () => api.audit(id), enabled: showHistory });

  if (item.isPending) return <p className="muted">Loading…</p>;
  if (item.isError) return <p className="error">{(item.error as Error).message}. <Link to="/">Back to the collection</Link></p>;
  const it = item.data;
  const shown = it.photos.find((p) => p.id === active) ?? it.photos.find((p) => p.id === it.cover_photo_id) ?? it.photos[0];
  const details = Object.entries(it.details).filter(([k, v]) => k !== "attributes" && v !== null && v !== "" && v !== false);
  const attributes = (it.details.attributes ?? {}) as Record<string, string>;

  const aiPhotos = it.photos.filter((p) => p.sha256).map((p) => ({ sha256: p.sha256!, role: p.role }));
  const raw = (it.item_type === "coin" || it.item_type === "bullion") && it.condition?.grading !== "slabbed";

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["item", id] });
    await qc.invalidateQueries({ queryKey: ["items"] });
    await qc.invalidateQueries({ queryKey: ["audit", id] });
  };

  return (
    <>
      <p className="crumbs"><Link to="/">Collection</Link></p>
      {note && <p className="error" role="alert">{note}</p>}
      <div className="page-head">
        <h1>{it.title}</h1>
        <div className="head-actions">
          {it.deleted_at ? (
            <button className="primary" onClick={async () => { await api.restoreItem(it.id); await refresh(); }}>Restore item</button>
          ) : (
            <>
              <button onClick={() => { setEditSeed(null); setEditing((e) => !e); }}>{editing ? "Close editor" : "Edit details"}</button>
              <button
                className="ghost danger"
                onClick={async () => {
                  if (!window.confirm(`Move “${it.title}” to the bin? You can restore it later.`)) return;
                  await api.deleteItem(it.id);
                  await qc.invalidateQueries({ queryKey: ["items"] });
                  navigate("/");
                }}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>
      {it.deleted_at && <p className="notice">This item is in the bin.</p>}

      <div className="item-layout">
        <div className="item-photos">
          {shown ? (
            <a href={shown.urls.edited ?? shown.urls.original} target="_blank" rel="noreferrer" className="hero-photo">
              <img src={shown.urls.medium} alt={`${ROLE_LABELS[shown.role]} of ${it.title}`} />
            </a>
          ) : (
            <div className="hero-photo empty-photo">No photos yet</div>
          )}
          {it.photos.length > 1 && (
            <div className="photo-strip" role="list">
              {it.photos.map((p) => (
                <button key={p.id} role="listitem" className={p.id === shown?.id ? "on" : ""} onClick={() => setActive(p.id)} aria-label={`Show ${ROLE_LABELS[p.role]}`}>
                  <img src={p.urls.thumb} alt="" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="item-facts">
          {editing ? (
            <ItemForm
              key={editSeed?.n ?? 0}
              item={it}
              defaults={editSeed?.defaults}
              submitLabel="Save changes"
              onCancel={() => { setEditing(false); setEditSeed(null); }}
              onSubmit={async (payload) => {
                await api.updateItem(it.id, it.version, payload);
                await qc.invalidateQueries({ queryKey: ["tags"] });
                await refresh();
                setEditing(false);
                setEditSeed(null);
              }}
            />
          ) : (
            <>
              {it.values && it.status !== "sold" && <ValuePanel item={it} />}
              <dl className="facts">
                <dt>Type</dt>
                <dd>{ITEM_TYPE_LABELS[it.item_type]}{it.quantity > 1 ? `, ${it.quantity} pieces` : ""}</dd>
                <dt>Status</dt>
                <dd>{STATUS_LABELS[it.status]}</dd>
                {grade(it) && (<><dt>Grade</dt><dd>{grade(it)}{it.condition?.cert_number ? `, cert ${it.condition.cert_number}` : ""}</dd></>)}
                {details.map(([k, v]) => (
                  <FactRow key={k} label={DETAIL_LABELS[k] ?? k} value={v === true ? "Yes" : tidyNumber(String(v))} />
                ))}
                {Object.entries(attributes).map(([k, v]) => (
                  <FactRow key={k} label={k} value={v} />
                ))}
                {it.location_path && <FactRow label="Stored in" value={it.location_path} />}
              </dl>

              <h2>Metal</h2>
              {it.metal_content.length ? (
                <table className="figures">
                  <thead>
                    <tr><th>Metal</th><th>Gross</th><th>Fineness</th><th>Pure per piece</th></tr>
                  </thead>
                  <tbody>
                    {it.metal_content.map((m, i) => (
                      <tr key={i}>
                        <td>{METAL_LABELS[m.metal]}</td>
                        <td className="tabular">{m.gross_weight_g ? `${Number(m.gross_weight_g)} g` : "—"}</td>
                        <td className="tabular">{m.fineness ? Number(m.fineness) : "—"}</td>
                        <td className="tabular">
                          {ozt(m.pure_toz)}
                          {m.source === "override" ? " (override)" : m.source === "reference" ? " (reference)" : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">
                  {it.details.composition
                    ? `No precious metal: ${String(it.details.composition).replace(/^./, (c) => c.toLowerCase())}. Melt value is only for gold, silver, platinum and palladium.`
                    : "No metal content recorded. Melt value needs it."}
                </p>
              )}

              <h2>Purchase</h2>
              <dl className="facts">
                <dt>Paid</dt>
                <dd className="tabular">{money(it.purchase_price)}{it.purchase_fees ? ` + ${money(it.purchase_fees)} fees` : ""}</dd>
                <dt>Cost basis</dt>
                <dd className="tabular">
                  {it.cost_basis ? money(it.cost_basis) : "Unknown"}
                  {it.cost_basis_status === "estimated" ? " (estimated)" : ""}
                </dd>
                {it.acquired_date && <FactRow label="Acquired" value={it.acquired_date} />}
                {it.purchase_source && <FactRow label="From" value={it.purchase_source} />}
                {it.status === "sold" && (
                  <>
                    <dt>Sold</dt>
                    <dd className="tabular">{money(it.sale_price)} on {it.sale_date}{it.sale_venue ? ` via ${it.sale_venue}` : ""}{it.sale_fees ? `, ${money(it.sale_fees)} fees` : ""}</dd>
                  </>
                )}
              </dl>
              {it.tags.length > 0 && (
                <p className="tags">{it.tags.map((t) => <Link key={t} to={`/?tag=${encodeURIComponent(t)}`} className="tag">{t}</Link>)}</p>
              )}
              {it.notes && <p className="notes">{it.notes}</p>}
            </>
          )}
        </div>
      </div>

      {!it.deleted_at && (
        <div className="item-sections">
          {it.status !== "sold" && <MarketValue item={it} />}
          {ai && aiPhotos.length > 0 && (
            <section className="ai-section" aria-labelledby="ai-item-h">
              <h2 id="ai-item-h">From the photos</h2>
              <div className="ai-cols">
                <div>
                  <h3>What is it?</h3>
                  <AiIdentify
                    photos={aiPhotos}
                    itemId={it.id}
                    useLabel="Edit with these details"
                    usedNote="The editor above has these details in the fields that were empty. Check them and save."
                    intro={<p className="hint">Fills in only what this item doesn't have yet; its title, prices and notes stay.</p>}
                    onUse={(defaults) => {
                      setEditSeed({ n: Date.now(), defaults: fillBlanks(it, defaults) });
                      setEditing(true);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  />
                </div>
                {raw && (
                  <div>
                    <h3>What grade?</h3>
                    <AiGradeGuess
                      photos={aiPhotos}
                      itemId={it.id}
                      onNote={async (text) => {
                        await api.updateItem(it.id, it.version, { notes: it.notes ? `${it.notes}\n\n${text}` : text });
                        await refresh();
                      }}
                    />
                  </div>
                )}
              </div>
            </section>
          )}
          <section>
            <h2>Photos</h2>
            <PhotoManager item={it} />
          </section>
          <section>
            <h2>Documents</h2>
            <Documents item={it} />
          </section>
          <section>
            <h2>History</h2>
            <button className="link" onClick={() => setShowHistory((s) => !s)}>{showHistory ? "Hide changes" : "Show changes to value-affecting fields"}</button>
            {showHistory && audit.data && (
              <table className="figures audit">
                <thead><tr><th>When</th><th>Field</th><th>From</th><th>To</th></tr></thead>
                <tbody>
                  {audit.data.map((a) => (
                    <tr key={a.id}>
                      <td>{new Date(a.at).toLocaleString()}</td>
                      <td>{a.field.replace(/_/g, " ")}</td>
                      <td>{a.old_value ?? "—"}</td>
                      <td>{a.new_value ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function ValuePanel({ item }: { item: Item }) {
  const v = item.values!;
  const cur = v.currency;
  const missing = v.melt_missing_spot.map((m) => METAL_LABELS[m as Metal] ?? m);
  const per = item.quantity > 1 && v.current ? Number(v.current) / item.quantity : null;
  let ruleText: string;
  if (v.rule_applied === "none") ruleText = "No value yet: add the metal content, or set a cost.";
  else if (v.rule === "max" && v.market === null) ruleText = "Using melt value. This item is valued at the higher of melt and market value, and there's no market value yet.";
  else if (v.rule === "max") ruleText = `Using ${RULE_LABELS[v.rule_applied] ?? v.rule_applied}, the higher of melt and market value.`;
  else ruleText = `Valued at ${RULE_LABELS[v.rule] ?? v.rule}.`;
  return (
    <section className="value-panel" aria-label="Value">
      <div className="value-main">
        <span className="kpi-label">Current value</span>
        <span className="value-big">{v.current ? money(v.current, cur) : "—"}</span>
        {per !== null && <span className="hint">{money(String(per), cur)} each</span>}
      </div>
      <dl className="facts">
        <dt>Melt</dt>
        <dd className="tabular">{money(v.melt, cur)}</dd>
        <dt>Market</dt>
        <dd className="tabular">
          {v.market ? money(v.market, cur) : <span className="hint">None yet</span>}
          {v.market && v.market_as_of && (
            <span className="hint"> as of {new Date(`${v.market_as_of}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>
          )}
        </dd>
        <dt>Paid</dt>
        <dd className="tabular">{v.cost ? money(v.cost, cur) : "Unknown"}</dd>
        {v.gain && (
          <>
            <dt>Gain</dt>
            <dd className={`tabular ${Number(v.gain) < 0 ? "is-loss" : ""}`}>{Number(v.gain) > 0 ? "+" : ""}{money(v.gain, cur)}</dd>
          </>
        )}
      </dl>
      <p className="hint">{ruleText}</p>
      {missing.length > 0 && <p className="hint">No spot price yet for {missing.join(" and ")}, so that part of the melt value is missing.</p>}
    </section>
  );
}

/** "100.000000" -> "100"; leaves anything that isn't a plain decimal alone (years, serials, text). */
function tidyNumber(v: string): string {
  return /^-?\d+\.\d+$/.test(v) ? String(Number(v)) : v;
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
