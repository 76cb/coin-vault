import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ago, api, BackupEntry } from "../api";

const size = (b: number | null | undefined) => {
  if (b == null) return "—";
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(b / 1e3))} KB`;
};
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Settings, Backups: nightly backups of the database and every file, Back up now, download, and how to restore. */
export default function Backups() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["backups"], queryFn: api.backups });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [time, setTime] = useState("03:15");

  useEffect(() => {
    if (q.data) {
      setEnabled(q.data.enabled);
      setTime(q.data.time);
    }
  }, [q.data]);

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["backups"] });
      if (ok) setNote(ok);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const d = q.data;
  const last = d?.last;
  const newest = d?.backups[0];
  const changed = d && (enabled !== d.enabled || time !== d.time);

  return (
    <section className="panel backups" aria-labelledby="backups-h">
      <h2 id="backups-h">Backups</h2>
      {q.isPending && <p className="muted">Loading…</p>}
      {q.isError && <p className="error">{(q.error as Error).message}</p>}
      {d && (
        <>
          <div className={`backup-status${last && last.ok === false ? " is-bad" : newest ? " is-good" : " is-none"}`} role="status">
            {last && last.ok === false ? (
              <>
                <strong>The last backup failed</strong> {last.at ? `(${ago(last.at)})` : ""}: {last.error}
              </>
            ) : newest ? (
              <>
                <strong>Last backup {ago(newest.created_at)}</strong>, {when(newest.created_at)}: {newest.counts.items ?? 0} items,{" "}
                {newest.counts.photos ?? 0} photos, {newest.counts.documents ?? 0} documents. Checked after it was made.
              </>
            ) : (
              <strong>No backups yet. Make the first one now; it copies every photo and document.</strong>
            )}
          </div>

          <div className="backup-actions">
            <button type="button" className="primary" disabled={busy} onClick={() => run(api.backupNow, "Backup made and checked.")}>
              {busy ? "Working…" : "Back up now"}
            </button>
            {newest && (
              <a className="button" href={api.backupDownloadUrl(newest.name)} download>
                Download the latest ({size(newest.download_bytes)})
              </a>
            )}
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          {note && <p className="success">{note}</p>}

          <form
            className="backup-schedule"
            onSubmit={(e) => { e.preventDefault(); run(() => api.backupSettings({ enabled, time }), "Schedule saved."); }}
          >
            <label className="check">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              Back up every night
            </label>
            <label>
              At
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={!enabled} required />
            </label>
            <span className="hint">{d.timezone.replace("_", " ")} time{d.next_run && d.enabled ? `; next ${when(d.next_run)}` : ""}</span>
            {changed && <button type="submit" disabled={busy}>Save schedule</button>}
          </form>

          {d.backups.length > 0 && (
            <table className="figures ledger backup-list">
              <thead>
                <tr><th>Made</th><th>Holds</th><th>Size</th><th aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {d.backups.map((b) => <Row key={b.name} b={b} busy={busy} onDelete={() => run(() => api.deleteBackup(b.name), "Backup deleted.")} />)}
              </tbody>
            </table>
          )}

          <details className="backup-help">
            <summary>Where backups are kept, and how to restore one</summary>
            <p>
              Backups are in <code>{d.folder}</code> on the server ({size(d.free_bytes)} free). Each holds the database at that moment;
              photos and documents are stored once and shared between backups, so a nightly backup only adds what's new. Kept: the
              last three, one a day for a week, one a week for a month, and one a month for a year.
            </p>
            <p>
              That folder is on the same disk as the collection, so also keep a copy somewhere else: download one now and then, or mount a
              NAS there (set <code>CV_BACKUP_DIR</code>). Keep a copy of <code>/etc/coinvault/coinvault.env</code> too: it holds the key that
              unlocks your saved provider API keys, and backups leave it out on purpose.
            </p>
            <p>To restore, run these in the container (from the Proxmox host, put <code>pct exec &lt;container id&gt; --</code> in front):</p>
            <pre>/opt/coinvault/app/deploy/lxc/restore.sh{"\n"}/opt/coinvault/app/deploy/lxc/restore.sh {newest?.name ?? "<name>"}</pre>
            <p>
              The first lists the backups; the second puts one back (it backs up the current state first, so a restore can be undone). For a
              downloaded copy, put the .tar in the container and give its path instead of a name. Updates also back up before they change anything.
            </p>
          </details>
        </>
      )}
    </section>
  );
}

function Row({ b, busy, onDelete }: { b: BackupEntry; busy: boolean; onDelete: () => void }) {
  return (
    <tr>
      <td>
        {when(b.created_at)}
        <span className="hint"> {b.reason === "nightly" ? "nightly" : "made by hand"}</span>
      </td>
      <td>
        {b.counts.items ?? 0} items, {b.files.toLocaleString()} files
        {!b.verified && <span className="error"> not checked</span>}
      </td>
      <td className="tabular">{size(b.download_bytes)}</td>
      <td className="backup-row-actions">
        <a className="button ghost small" href={api.backupDownloadUrl(b.name)} download>Download</a>
        <button
          type="button"
          className="ghost small danger"
          disabled={busy}
          onClick={() => window.confirm(`Delete the backup from ${when(b.created_at)}? Photos other backups still use are kept.`) && onDelete()}
        >
          Delete
        </button>
      </td>
    </tr>
  );
}
