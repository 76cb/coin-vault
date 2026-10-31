import { ClipboardEvent, FormEvent, useEffect, useRef, useState } from "react";

import { api, certNumber, Described, ITEM_TYPE_LABELS, money, PcgsLookup, pcgsNumberGrade, PcgsQuery } from "../api";
import { defaultsFromDescription, defaultsFromNumista, defaultsFromPcgs, FormState } from "./ItemForm";
import NumistaSearch, { numistaQuery } from "./NumistaSearch";

export type AfterSave = { pcgsPriceGuide?: boolean };

/** Paste a listing title, describe the piece, or give a PCGS cert number; the form below is filled from it. */
export default function QuickStart({ onUse }: { onUse: (defaults: Partial<FormState>, after?: AfterSave) => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Described | null>(null);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [numista, setNumista] = useState(false);
  const [pcgsOpen, setPcgsOpen] = useState(false);
  const pasted = useRef(false);
  const seq = useRef(0);
  const cert = certNumber(text);
  const numberGrade = cert ? null : pcgsNumberGrade(text);
  const pcgsQuery: PcgsQuery | null = cert ? { cert_no: cert } : numberGrade;

  useEffect(() => {
    const t = text.trim();
    if (t.length < 3 || certNumber(t) || pcgsNumberGrade(t)) {
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
      <p className="hint qs-also">A PCGS number and grade works too, like “9801 MS65”.</p>
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
      {pcgsQuery && <PcgsFind key={JSON.stringify(pcgsQuery)} query={pcgsQuery} onUse={onUse} />}
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
      {!pcgsQuery && (pcgsOpen ? <PcgsPanel onUse={onUse} onClose={() => setPcgsOpen(false)} /> : null)}
      {!pcgsQuery && (
        numista ? (
          <NumistaSearch
            start={numistaQuery(text, result)}
            hint={[text, result?.condition?.grade_text ?? "", ...(result?.condition?.designations ?? [])].join(" ")}
            actionLabel="Fill in from Numista"
            doneLabel="Filled in below."
            onPick={(t, issue) => onUse(defaultsFromNumista(t, issue, result ? defaultsFromDescription(result) : { title: text.trim() }))}
            onCancel={() => setNumista(false)}
          />
        ) : (
          <span className="qs-links">
            <button type="button" className="ghost small qs-numista" onClick={() => setNumista(true)}>
              {text.trim() ? "Look this up on Numista" : "Search the Numista catalogue"}
            </button>
            {!pcgsOpen && (
              <button type="button" className="ghost small" onClick={() => setPcgsOpen(true)}>Look up at PCGS by number and grade or barcode</button>
            )}
          </span>
        )
      )}
    </section>
  );
}

/** What a lookup asks for, in words: for the button and the messages. */
function describeQuery(q: PcgsQuery): string {
  if ("cert_no" in q) return `cert ${q.cert_no}`;
  if ("pcgs_no" in q) return `PCGS #${q.pcgs_no} in ${q.grade}`;
  return `${q.service} barcode ${q.barcode}`;
}

/** One PCGS lookup, only when asked: each one counts against the day's PCGS allowance. */
function PcgsFind({ query, onUse, auto = false }: { query: PcgsQuery; onUse: (defaults: Partial<FormState>, after?: AfterSave) => void; auto?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<PcgsLookup | null>(null);
  const [usePrice, setUsePrice] = useState(true);
  const [applied, setApplied] = useState(false);
  const started = useRef(false);

  const look = async () => {
    setBusy(true);
    setError(null);
    try {
      setFound(await api.pcgsLookup(query));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (auto && !started.current) {
      started.current = true;
      void look();
    }
  });

  if (!found) {
    return (
      <div className="qs-result qs-pcgs">
        {!auto && <p>{"cert_no" in query ? "This looks like a PCGS cert number." : "This looks like a PCGS number and grade."}</p>}
        {(!auto || error) && (
          <button type="button" className="primary" onClick={look} disabled={busy}>
            {busy ? "Looking up…" : `Look up ${describeQuery(query)} at PCGS`}
          </button>
        )}
        {auto && busy && <p className="hint">Looking up {describeQuery(query)} at PCGS…</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    );
  }

  const c = found.coin;
  const thumb = c.images.find((i) => i.thumbnail)?.thumbnail;
  const slab = found.condition.grading_service;
  return (
    <div className="qs-result qs-pcgs" role="status">
      <div className="pcgs-card">
        {thumb && <img src={thumb} alt="" className="pcgs-thumb" referrerPolicy="no-referrer" />}
        <div>
          <p className="pcgs-name"><strong>{c.name ?? "PCGS coin"}</strong></p>
          <p>
            {[slab, c.grade, found.condition.designations.join(", ")].filter(Boolean).join(" ")}
            {found.condition.cert_number ? `, cert ${found.condition.cert_number}` : ""}
            {c.pcgs_no ? `, PCGS #${c.pcgs_no}` : ""}
          </p>
          {c.price_guide && <p>Price guide <span className="tabular">{money(c.price_guide, "USD")}</span>{slab ? "" : ` in ${c.grade}`}</p>}
          {c.population != null && (
            <p className="hint">PCGS population {c.population.toLocaleString()} at this grade, {(c.pop_higher ?? 0).toLocaleString()} higher</p>
          )}
          {c.coinfacts_link && <p><a href={c.coinfacts_link} target="_blank" rel="noreferrer">CoinFacts page</a></p>}
          {!found.metal && <p className="hint">PCGS gave no metal content; add it below if the coin has precious metal.</p>}
          {!slab && <p className="hint">Looked up by grade, so the form marks it raw; change it to slabbed below if it's in a holder.</p>}
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

type PcgsMode = "grade" | "barcode";

/** Look up at PCGS by a PCGS number and grade (any coin, raw or NGC too), or by a PCGS or NGC holder's barcode. */
function PcgsPanel({ onUse, onClose }: { onUse: (defaults: Partial<FormState>, after?: AfterSave) => void; onClose: () => void }) {
  const [mode, setMode] = useState<PcgsMode>("grade");
  const [number, setNumber] = useState("");
  const [grade, setGrade] = useState("");
  const [barcode, setBarcode] = useState("");
  const [service, setService] = useState<"PCGS" | "NGC">("PCGS");
  const [query, setQuery] = useState<PcgsQuery | null>(null);
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<string | null>(null);

  const readPhoto = async (file: File | undefined) => {
    if (!file) return;
    setReading(true);
    setReadNote(null);
    try {
      const codes = await api.pcgsReadBarcode(file);
      if (!codes.length) setReadNote("No barcode found in that photo. Try a sharper, closer photo of the label, or type the number under the barcode.");
      else {
        setBarcode(codes[0].text);
        setQuery(null);
        setReadNote(codes.length > 1 ? `Found ${codes.length} barcodes; using the first. Check it's the one on the label.` : "Read the barcode from the photo.");
      }
    } catch (err) {
      setReadNote((err as Error).message);
    } finally {
      setReading(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setQuery(mode === "grade" ? { pcgs_no: number.trim(), grade: grade.trim() } : { barcode: barcode.trim(), service });
  };

  return (
    <div className="qs-result qs-pcgs-panel">
      <div className="qs-pcgs-head">
        <div className="segmented" role="radiogroup" aria-label="Look up at PCGS by">
          <button type="button" role="radio" aria-checked={mode === "grade"} className={mode === "grade" ? "on" : ""} onClick={() => { setMode("grade"); setQuery(null); }}>PCGS number and grade</button>
          <button type="button" role="radio" aria-checked={mode === "barcode"} className={mode === "barcode" ? "on" : ""} onClick={() => { setMode("barcode"); setQuery(null); }}>Holder barcode</button>
        </div>
        <button type="button" className="ghost small" onClick={onClose}>Close</button>
      </div>
      <form className="qs-pcgs-form" onSubmit={submit}>
        {mode === "grade" ? (
          <>
            <label>
              PCGS number
              <input value={number} onChange={(e) => { setNumber(e.target.value); setQuery(null); }} inputMode="numeric" placeholder="9801" required />
            </label>
            <label>
              Grade
              <input value={grade} onChange={(e) => { setGrade(e.target.value); setQuery(null); }} placeholder="MS65 or 64+" required />
            </label>
            <p className="hint">For any coin, raw or graded by anyone: the PCGS number is on PCGS CoinFacts and on PCGS labels.</p>
          </>
        ) : (
          <>
            <fieldset className="qs-service">
              <legend>Holder</legend>
              {(["PCGS", "NGC"] as const).map((sv) => (
                <label key={sv} className="check">
                  <input type="radio" name="pcgs-service" checked={service === sv} onChange={() => { setService(sv); setQuery(null); }} /> {sv}
                </label>
              ))}
            </fieldset>
            <label>
              Barcode
              <input value={barcode} onChange={(e) => { setBarcode(e.target.value); setQuery(null); }} placeholder="Scan it, or type the digits under the barcode" required />
            </label>
            <label className="button ghost small qs-read">
              {reading ? "Reading…" : "Read it from a photo of the label"}
              <input type="file" accept="image/*" className="visually-hidden" onChange={(e) => { void readPhoto(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            {readNote && <p className="hint" role="status">{readNote}</p>}
          </>
        )}
        <button type="submit" className="primary">Look up at PCGS</button>
      </form>
      {query && <PcgsFind key={JSON.stringify(query)} query={query} onUse={onUse} auto />}
    </div>
  );
}
