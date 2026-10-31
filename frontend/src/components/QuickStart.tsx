import { ClipboardEvent, useEffect, useRef, useState } from "react";

import { api, Described, ITEM_TYPE_LABELS } from "../api";

/** Paste a listing title (or type a description); the form below is filled from it. */
export default function QuickStart({ onUse }: { onUse: (d: Described) => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<Described | null>(null);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pasted = useRef(false);
  const seq = useRef(0);

  useEffect(() => {
    const t = text.trim();
    if (t.length < 3) {
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
          onUse(d);
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
      <label id="qs-h" htmlFor="qs-text">Paste the listing title, or describe it</label>
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
            <button type="button" className="primary" onClick={() => { onUse(result); setApplied(true); }}>
              Fill in the form
            </button>
          )}
        </div>
      )}
    </section>
  );
}
