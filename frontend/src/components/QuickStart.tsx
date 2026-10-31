import { ClipboardEvent, useEffect, useRef, useState } from "react";

import { api, certNumber, Described, ITEM_TYPE_LABELS, money, PcgsLookup } from "../api";
import { defaultsFromDescription, defaultsFromPcgs, FormState } from "./ItemForm";

export type AfterSave = { pcgsPriceGuide?: boolean };

/** Paste a listing title, describe the piece, or give a PCGS cert number; the form below is filled from it. */
export default function QuickStart({ onUse }: { onUse: (defaults: Partial<FormState>, after?: AfterSave) => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Described | null>(null);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pasted = useRef(false);
  const seq = useRef(0);
  const cert = certNumber(text);

  useEffect(() => {
    const t = text.trim();
    if (t.length < 3 || certNumber(t)) {
      setResult(null);
      return;
    }
    const n = ++seq.current;
    const timer = window.setTimeout(async () => {
      try {
        const d = await api.describe(t);
        if (n !== seq.current) return; // a newer keystroke won
        setResult(d);
        setError(null);
        if (pasted.current) {
          pasted.current = false;
          onUse(defaultsFromDescription(d));
          setApplied(true);
        } else {
          setApplied(false);
        }
      } catch (err) {
        setError((err as Error).message);
      }
    }, pasted.current ? 0 : 350);
    return () => window.clearTimeout(timer);
  }, [text, onUse]);

  const best = result?.compositions[0];
  const tied = result ? result.compositions.filter((c) => best && c.score === best.score) : [];

  return (
    <section className="quickstart">
      <label id="qs-h" htmlFor="qs-text">Paste the listing title, describe it, or enter a PCGS certificate number</label>
      <textarea
        id="qs-text"
        rows={2}
        value={text}
        placeholder="2021 $1 Silver Eagle T2 First Production PCGS MS70"
        onChange={(e) => setText(e.target.value)}
        onPaste={(_e: ClipboardEvent) => { pasted.current = true; }}
        autoFocus
      />
      {error && <p className="error" role="alert">{error}</p>}
      {cert && <PcgsCert key={cert} cert={cert} onUse={onUse} />}
      {result && (
        <div className="qs-result" role="status">
          <ul className="qs-found">
            <li><strong>{ITEM_TYPE_LABELS[result.item_type]}</strong></li>
            {result.recognized.filter((r) => r !== "banknote").map((r) => <li key={r}>{r}</li>)}
            {result.quantity > 1 && !result.recognized.some((r) => r.startsWith("quantity")) && <li>quantity {result.quantity}</li>}
          </ul>
          <p className="hint qs-metal">
            {tied.length === 1 && best
              ? `Metal: ${best.label}, ${Number(best.pure_toz).toLocaleString(undefined, { maximumFractionDigits: 4 })} oz pure.`
              : tied.length > 1
                ? `Metal: could be ${tied.map((c) => c.label).join(" or ")}; pick one below.`
                : result.item_type === "banknote" || result.item_type === "other"
                  ? ""
                  : "Metal content not recognised; add it below."}
          </p>
          {applied ? (
            <p className="success qs-applied">Filled in below. Add what you paid, check it, and save.</p>
          ) : (
            <button type="button" className="primary" onClick={() => { onUse(defaultsFromDescription(result)); setApplied(true); }}>
              Fill in the form
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/** One PCGS lookup, only when asked: each one counts against the day's PCGS allowance. */
function PcgsCert({ cert, onUse }: { cert: string; onUse: (defaults: Partial<FormState>, after?: AfterSave) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<PcgsLookup | null>(null);
  const [usePrice, setUsePrice] = useState(true);
  const [applied, setApplied] = useState(false);

  const look = async () => {
    setBusy(true);
    setError(null);
    try {
      setFound(await api.pcgsLookup(cert));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!found) {
    return (
      <div className="qs-result qs-pcgs">
        <p>This looks like a PCGS cert number.</p>
        <button type="button" className="primary" onClick={look} disabled={busy}>
          {busy ? "Looking up…" : `Look up cert ${cert} at PCGS`}
        </button>
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    );
  }

  const c = found.coin;
  const thumb = c.images.find((i) => i.thumbnail)?.thumbnail;
  return (
    <div className="qs-result qs-pcgs" role="status">
      <div className="pcgs-card">
        {thumb && <img src={thumb} alt="" className="pcgs-thumb" referrerPolicy="no-referrer" />}
        <div>
          <p className="pcgs-name"><strong>{c.name ?? "PCGS coin"}</strong></p>
          <p>PCGS {[c.grade, found.condition.designations.join(", ")].filter(Boolean).join(" ")}, cert {c.cert_no}</p>
          {c.price_guide && <p>Price guide <span className="tabular">{money(c.price_guide, "USD")}</span></p>}
          {c.population != null && (
            <p className="hint">Population {c.population.toLocaleString()} at this grade, {(c.pop_higher ?? 0).toLocaleString()} higher</p>
          )}
          {c.coinfacts_link && <p><a href={c.coinfacts_link} target="_blank" rel="noreferrer">CoinFacts page</a></p>}
          {!found.metal && <p className="hint">PCGS gave no metal content; add it below if the coin has precious metal.</p>}
        </div>
      </div>
      {c.price_guide && (
        <label className="check">
          <input type="checkbox" checked={usePrice} onChange={(e) => setUsePrice(e.target.checked)} />
          Save the PCGS price guide value as its market value
        </label>
      )}
      {applied ? (
        <p className="success qs-applied">Filled in below. Add what you paid, check it, and save.</p>
      ) : (
        <button type="button" className="primary" onClick={() => { onUse(defaultsFromPcgs(found), { pcgsPriceGuide: Boolean(c.price_guide) && usePrice }); setApplied(true); }}>
          Fill in the form
        </button>
      )}
    </div>
  );
}
