import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ago, api, UpdateSource, ValueUpdates as Status } from "../api";

const DAYS: [Status["day"], string][] = [
  ["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"],
];
// dateStyle/timeStyle can't be combined with weekday (browsers throw), so the parts are spelled out
const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

function sourceLine(name: string, s: UpdateSource | undefined): string | null {
  if (!s) return null;
  if (s.stopped && !s.checked) return `${name}: stopped, ${s.stopped.charAt(0).toLowerCase()}${s.stopped.slice(1)}`;
  if (!s.checked && !s.failed) return `${name}: nothing was due.`;
  const parts = [`${plural(s.checked, "value")} checked`, `${s.changed} changed`];
  if (s.failed) parts.push(`${s.failed} couldn't be updated`);
  return `${name}: ${parts.join(", ")}${s.stopped ? `; then stopped: ${s.stopped}` : "."}`;
}

/** Settings, Value updates: once a week, the PCGS price guide values and Numista estimates you've fetched are fetched again. */
export default function ValueUpdates() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["value-updates"],
    queryFn: api.valueUpdates,
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });
  const [enabled, setEnabled] = useState(true);
  const [day, setDay] = useState<Status["day"]>("sun");
  const [time, setTime] = useState("05:40");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const wasRunning = useRef({ v: false }).current;

  useEffect(() => {
    if (!q.data) return;
    setEnabled(q.data.enabled);
    setDay(q.data.day);
    setTime(q.data.time);
    if (wasRunning.v && !q.data.running) {
      // finished: the item pages and dashboard have new values
      void qc.invalidateQueries({ queryKey: ["items"] });
      void qc.invalidateQueries({ queryKey: ["item"] });
      void qc.invalidateQueries({ queryKey: ["summary"] });
      void qc.invalidateQueries({ queryKey: ["value-history"] });
    }
    wasRunning.v = q.data.running;
  }, [q.data, qc, wasRunning]);

  const run = async (fn: () => Promise<Status>, ok?: string) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      qc.setQueryData(["value-updates"], await fn());
      if (ok) setNote(ok);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const d = q.data;
  const last = d?.last;
  const changed = d && (enabled !== d.enabled || day !== d.day || time !== d.time);
  const tracked = d ? d.tracked_pcgs + d.tracked_numista : 0;

  return (
    <section className="panel value-updates" aria-labelledby="updates-h">
      <h2 id="updates-h">Value updates</h2>
      <p className="hint lede">
        Once a week, the PCGS price guide values and Numista estimates you've fetched for your items are fetched again. A new value is saved
        with its date, so the value history shows the change; an unchanged one is just marked as checked. Items join by fetching a value
        once (on the item page, or when adding from PCGS). A value you chose with “Use this” stays chosen.
      </p>
      {q.isPending && <p className="muted">Loading…</p>}
      {q.isError && <p className="error">{(q.error as Error).message}</p>}
      {d && (
        <>
          <p>
            {tracked
              ? `Following ${[d.tracked_pcgs ? plural(d.tracked_pcgs, "item") + " with a PCGS value" : "", d.tracked_numista ? plural(d.tracked_numista, "item") + " with a Numista estimate" : ""].filter(Boolean).join(" and ")}.`
              : "No items to follow yet: fetch a PCGS price guide value or a Numista estimate on an item first."}
          </p>
          <div className={`backup-status${last && !last.ok ? " is-bad" : last ? " is-good" : " is-none"}`} role="status">
            {d.running ? (
              <strong>Updating values now…</strong>
            ) : last ? (
              <>
                <strong>{last.ok ? "Last update" : "The last update failed"} {ago(last.finished_at ?? last.started_at)}</strong>
                <ul className="updates-lines">
                  {[sourceLine("PCGS", last.pcgs), sourceLine("Numista", last.numista)].filter(Boolean).map((l) => <li key={l}>{l}</li>)}
                  {last.errors.slice(0, 5).map((e) => <li key={e} className="hint">{e}</li>)}
                </ul>
              </>
            ) : (
              <strong>No update has run yet.</strong>
            )}
          </div>
          <div className="backup-actions">
            <button type="button" className="primary" disabled={busy || d.running || !tracked} onClick={() => run(api.runValueUpdates)}>
              {d.running ? "Updating…" : "Update now"}
            </button>
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          {note && <p className="success">{note}</p>}
          <form className="backup-schedule" onSubmit={(e) => { e.preventDefault(); run(() => api.valueUpdateSettings({ enabled, day, time }), "Schedule saved."); }}>
            <label className="check">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              Update every week
            </label>
            <label>
              On
              <select value={day} onChange={(e) => setDay(e.target.value as Status["day"])} disabled={!enabled}>
                {DAYS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
            <label>
              At
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={!enabled} required />
            </label>
            <span className="hint">{d.timezone.replace("_", " ")} time{d.next_run && d.enabled ? `; next ${when(d.next_run)}` : ""}</span>
            {changed && <button type="submit" disabled={busy}>Save schedule</button>}
          </form>
          <p className="hint">
            Each update uses one PCGS lookup per PCGS value (PCGS allows 1,000 a day) and about one Numista request per estimate (from your
            monthly allowance); it stops for the week if your cap in Data providers is reached.
          </p>
        </>
      )}
    </section>
  );
}
