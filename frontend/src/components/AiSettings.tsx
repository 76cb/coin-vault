import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";

import { AiCheck, AiSettings as Saved, api } from "../api";

const gb = (bytes: number | null) => (bytes ? `${(bytes / 1e9).toFixed(1)} GB` : "");

/** Settings, AI: the Ollama server on your network that looks at photos, and which of its models to use. */
export default function AiSettings() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ai-settings"], queryFn: api.aiSettings });
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");
  const [check, setCheck] = useState<AiCheck | null>(null);
  const [busy, setBusy] = useState<"check" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!q.data) return;
    setUrl(q.data.url);
    setModel(q.data.model ?? "");
  }, [q.data]);

  const runCheck = async (e?: FormEvent) => {
    e?.preventDefault();
    setBusy("check");
    setError(null);
    setNote(null);
    try {
      const c = await api.aiCheck(url);
      setCheck(c);
      setUrl(c.url);
      const seeing = c.models.filter((m) => m.vision);
      if (!seeing.some((m) => m.name === model)) setModel(seeing[0]?.name ?? "");
    } catch (err) {
      setCheck(null);
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const save = async (body: { url: string; model: string }, ok: string) => {
    setBusy("save");
    setError(null);
    setNote(null);
    try {
      const s: Saved = await api.saveAiSettings(body);
      qc.setQueryData(["ai-settings"], s);
      await qc.invalidateQueries({ queryKey: ["ai"] });
      setNote(ok);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const d = q.data;
  const seeing = check?.models.filter((m) => m.vision) ?? [];
  const blind = check?.models.filter((m) => !m.vision) ?? [];

  return (
    <section className="panel ai-settings" aria-labelledby="ai-h">
      <h2 id="ai-h">AI</h2>
      <p className="hint lede">
        A vision model on your own network can identify a piece from its photos, read a grading holder's label, and suggest a grade for a
        raw coin. Coin Vault uses <a href="https://ollama.com" target="_blank" rel="noreferrer">Ollama</a> for this; photos go only to the
        server you give here. The README explains setting one up on your Proxmox server with the GPU.
      </p>
      {q.isPending && <p className="muted">Loading…</p>}
      {q.isError && <p className="error">{(q.error as Error).message}</p>}
      {d && (
        <>
          <div className={`backup-status${d.ready ? " is-good" : " is-none"}`} role="status">
            <strong>{d.ready ? `On: ${d.model} at ${d.url.replace(/^https?:\/\//, "")}` : "Off: no AI server set up."}</strong>
          </div>
          <form className="ai-form" onSubmit={runCheck}>
            <label>
              Ollama address
              <input value={url} onChange={(e) => { setUrl(e.target.value); setCheck(null); }} placeholder="http://192.168.1.80:11434" inputMode="url" required />
            </label>
            <button type="submit" disabled={busy !== null || !url.trim()}>{busy === "check" ? "Checking…" : "Check the server"}</button>
          </form>
          {check && (
            <div className="ai-models">
              <p>
                Ollama {check.version} is answering.{" "}
                {seeing.length ? "Choose the model to use:" : "It has no model that can see photos yet. Download one on the server, then check again."}
              </p>
              {seeing.length > 0 && (
                <ul className="ai-model-list" role="radiogroup" aria-label="Model">
                  {seeing.map((m) => (
                    <li key={m.name}>
                      <label className="check">
                        <input type="radio" name="ai-model" value={m.name} checked={model === m.name} onChange={() => setModel(m.name)} />
                        <span><strong>{m.name}</strong> <span className="hint">{[m.parameter_size, m.quantization, gb(m.size)].filter(Boolean).join(", ")}</span></span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
              {blind.length > 0 && <p className="hint">Can't see photos, so not offered: {blind.map((m) => m.name).join(", ")}.</p>}
              {!seeing.length && <pre className="ai-cmd">ollama pull gemma4:26b</pre>}
              <div className="backup-actions">
                <button type="button" className="primary" disabled={busy !== null || !model} onClick={() => save({ url, model }, "Saved. The AI buttons now show on items, Add item and Upload photos.")}>
                  {busy === "save" ? "Saving…" : "Use this model"}
                </button>
              </div>
            </div>
          )}
          {d.ready && !check && (
            <div className="backup-actions">
              <button type="button" className="ghost small danger" disabled={busy !== null} onClick={() => save({ url: "", model: "" }, "Photo AI is off.")}>Turn off</button>
            </div>
          )}
          {error && <p className="error" role="alert">{error}</p>}
          {note && <p className="success" role="status">{note}</p>}
        </>
      )}
    </section>
  );
}
