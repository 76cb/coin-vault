import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, Item } from "../api";
import DropZone from "./DropZone";

const KINDS = [
  ["receipt", "Receipt"],
  ["invoice", "Invoice"],
  ["certificate", "Certificate"],
  ["assay_card", "Assay card"],
  ["other", "Other"],
] as const;

export default function Documents({ item }: { item: Item }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState("receipt");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["item", item.id] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="documents" aria-label="Documents">
      {item.documents.length > 0 ? (
        <ul className="doc-list">
          {item.documents.map((d) => (
            <li key={d.id}>
              <a href={d.url} target="_blank" rel="noreferrer">{d.title}</a>
              <span className="hint">{KINDS.find(([k]) => k === d.kind)?.[1] ?? d.kind}{d.doc_date ? `, ${d.doc_date}` : ""}</span>
              <button className="ghost small danger" disabled={busy} onClick={() => window.confirm(`Delete “${d.title}”?`) && run(() => api.deleteDocument(d.id))}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">Keep receipts, invoices, certificates and assay cards with the item.</p>
      )}
      <div className="doc-add">
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
        <DropZone
          label="Attach a document"
          hint="PDF or a photo, up to 25 MB."
          accept="application/pdf,image/*"
          multiple={false}
          disabled={busy}
          onFiles={([file]) => run(() => api.uploadDocument(file, { kind, item_ids: [item.id] }))}
        />
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
