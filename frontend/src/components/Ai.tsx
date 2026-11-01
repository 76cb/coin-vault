import { useQuery } from "@tanstack/react-query";
import { ReactNode, useState } from "react";
import { Link } from "react-router-dom";

import { AiGrade, AiIdentify as Identified, AiMatch, AiPhotoRef, api, ITEM_TYPE_LABELS, PcgsQuery } from "../api";
import { defaultsFromDescription, FormState } from "./ItemForm";
import { AfterSave, PcgsFind } from "./QuickStart";

/** Whether an admin has set up photo AI; pages only offer it when it's there. */
export function useAiReady(): boolean {
  const q = useQuery({ queryKey: ["ai"], queryFn: api.aiStatus, staleTime: 60_000 });
  return Boolean(q.data?.ready);
}

const WAIT = "Looking at the photos… The first one after a while takes longer, while the model loads.";

/** The PCGS lookup a holder's label or barcode allows: a PCGS cert, else a PCGS or NGC barcode. */
function pcgsQueryFor(r: Identified): { query: PcgsQuery; intro: string } | null {
  const h = r.holder;
  if (h?.service === "PCGS" && h.cert_number) return { query: { cert_no: h.cert_number.replace(/\D/g, "") }, intro: `The label reads PCGS cert ${h.cert_number}.` };
  const code = r.barcodes.find((b) => /^\d{8,20}$/.test(b.text));
  if (code && (h?.service === "PCGS" || h?.service === "NGC")) {
    return { query: { barcode: code.text, service: h.service }, intro: `The ${h.service} holder's barcode reads ${code.text}.` };
  }
  return null;
}

function Matches({ title, items }: { title: string; items: AiMatch[] }) {
  return (
    <div className="ai-matches">
      <p><strong>{title}</strong></p>
      <ul>
        {items.map((m) => (
          <li key={m.id}>
            {m.thumb ? <img src={m.thumb} alt="" /> : <span className="item-pick-empty" />}
            <span>
              <Link to={`/items/${m.id}`}>{m.title}</Link>
              {m.quantity > 1 && <span className="hint"> ({m.quantity} pieces)</span>}
              {m.why === "similar" && <span className="hint"> (a near copy of the photo)</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Ask the AI what the piece in these photos is. `onUse` gets starting values for the item form. */
export function AiIdentify({
  photos,
  itemId,
  onUse,
  useLabel = "Fill in the form",
  usedNote = "Filled in below. Check it, add what you paid, and save.",
  extra,
  intro,
}: {
  photos: AiPhotoRef[];
  itemId?: number;
  onUse?: (defaults: Partial<FormState>, after?: AfterSave) => void;
  useLabel?: string;
  usedNote?: string;
  extra?: (r: Identified) => ReactNode;
  intro?: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [r, setR] = useState<Identified | null>(null);
  const [applied, setApplied] = useState(false);

  const look = async () => {
    setBusy(true);
    setError(null);
    setApplied(false);
    try {
      setR(await api.aiIdentify(photos, itemId));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const pcgs = r ? pcgsQueryFor(r) : null;
  const h = r?.holder;
  const kinds = r ? r.described.recognized.filter((x) => x !== "banknote") : [];

  return (
    <div className="ai-box">
      {!r && intro}
      <div className="ai-go">
        <button type="button" className={r ? "ghost small" : ""} onClick={look} disabled={busy || !photos.length}>
          {busy ? "Looking…" : r ? "Ask again" : `Identify from ${photos.length === 1 ? "the photo" : "the photos"}`}
        </button>
        {busy && <span className="hint" role="status">{WAIT}</span>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {r && !busy && (
        <div className="ai-result" role="status">
          <p className="ai-verdict">
            <strong>{r.title}</strong>
            <span className={`ai-conf is-${r.confidence}`}>{r.confidence === "high" ? "Clear read" : r.confidence === "medium" ? "Fairly sure" : "Unsure"}</span>
          </p>
          <ul className="qs-found">
            <li><strong>{ITEM_TYPE_LABELS[r.described.item_type]}</strong></li>
            {kinds.map((x) => <li key={x}>{x}</li>)}
            {r.weight_text && <li>“{r.weight_text}”</li>}
          </ul>
          {h && (
            <p className="ai-holder">
              In a {h.service ?? "grading"} holder{h.grade ? `, graded ${h.grade}` : ""}{h.cert_number ? `, cert ${h.cert_number}` : ""}
              {h.pcgs_number ? `, PCGS #${h.pcgs_number}` : ""}.
            </p>
          )}
          {r.notes && <p className="hint">{r.notes}</p>}
          {r.same_photos.length > 0 && <Matches title={r.same_photos.length === 1 ? "This photo is already on an item:" : "These photos are already on items:"} items={r.same_photos} />}
          {r.same_coin.length > 0 && <Matches title="You may already have this:" items={r.same_coin} />}
          {pcgs && onUse && <PcgsFind key={JSON.stringify(pcgs.query)} query={pcgs.query} onUse={onUse} intro={`${pcgs.intro} PCGS's own details are the most reliable.`} />}
          {onUse && (applied ? (
            <p className="success qs-applied">{usedNote}</p>
          ) : (
            <button type="button" className="primary" onClick={() => { onUse(defaultsFromDescription(r.described)); setApplied(true); }}>{useLabel}</button>
          ))}
          {extra?.(r)}
          <p className="hint ai-foot">Read by {r.model} in {r.seconds.toLocaleString()} s. AI can misread a date or mint mark: check before you save.</p>
        </div>
      )}
    </div>
  );
}

/** A grade range for a raw coin from its photos, with what it saw. Offered as a guide, never as a grade. */
export function AiGradeGuess({ photos, itemId, onNote }: { photos: AiPhotoRef[]; itemId?: number; onNote?: (text: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [g, setG] = useState<AiGrade | null>(null);
  const [saved, setSaved] = useState(false);

  const look = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setG(await api.aiGrade(photos, itemId));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const range = g ? (g.low === g.high ? g.low : `${g.low} to ${g.high}`) : "";

  return (
    <div className="ai-box">
      <div className="ai-go">
        <button type="button" className={g ? "ghost small" : ""} onClick={look} disabled={busy || !photos.length}>
          {busy ? "Looking…" : g ? "Ask again" : "Suggest a grade"}
        </button>
        {busy && <span className="hint" role="status">{WAIT}</span>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {g && !busy && (
        <div className="ai-result" role="status">
          <p className="ai-verdict"><span className="ai-range tabular">{range}</span></p>
          <p>{g.summary}</p>
          <dl className="ai-grade-notes">
            {g.wear && (<><dt>Wear</dt><dd>{g.wear}</dd></>)}
            {g.surfaces && (<><dt>Surfaces</dt><dd>{g.surfaces}</dd></>)}
            {g.high_number >= 60 && (<><dt>Marks</dt><dd>{g.marks?.length ? g.marks.join("; ") : "None seen"}</dd></>)}
            <dt>Problems</dt>
            <dd>{g.problems.length ? g.problems.join("; ") : "None seen"}</dd>
            {g.photo_advice && (<><dt>Better photos</dt><dd>{g.photo_advice}</dd></>)}
          </dl>
          <p className="ai-caution">
            {g.low_number >= 60
              ? `Mint state: no wear. The exact MS grade depends on marks too small for photos to show, so check with a loupe${g.marks?.length ? "; the marks listed above may not be real" : ""}. For anything worth grading, send it to PCGS or NGC.`
              : "A guess from photos, not a grade. Lighting and angle hide wear, cleaning and hairlines. For anything worth grading, send it to PCGS or NGC."}
          </p>
          {onNote && (saved ? (
            <p className="success">Added to the item's notes.</p>
          ) : (
            <button type="button" onClick={async () => {
              try {
                await onNote(`Grade suggestion from photos (${g.model}, ${new Date().toLocaleDateString(undefined, { dateStyle: "medium" })}): ${range}. ${g.summary}${g.problems.length ? ` Possible problems: ${g.problems.join("; ")}.` : ""}`);
                setSaved(true);
              } catch (err) {
                setError((err as Error).message);
              }
            }}>
              Add to the item's notes
            </button>
          ))}
          <p className="hint ai-foot">Suggested by {g.model} in {g.seconds.toLocaleString()} s.</p>
        </div>
      )}
    </div>
  );
}
