import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";

import { ago, api, AppSettings, Provider, ProviderUsage } from "../api";

function useRun() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, run };
}

// Quota periods start at midnight UTC, so show them in UTC or Oct 1 reads as Sep 30 in the Americas.
const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

export function PriceSettings() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState<AppSettings | null>(null);
  const [saved, setSaved] = useState(false);
  const { error, busy, run } = useRun();
  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);
  if (!form) return null;

  const save = (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);
    run(async () => {
      const out = await api.patchSettings({
        base_currency: form.base_currency,
        spot_poll_minutes: Number(form.spot_poll_minutes),
        spot_stale_minutes: Number(form.spot_stale_minutes),
        spot_pause_weekends: form.spot_pause_weekends,
      });
      qc.setQueryData(["settings"], out);
      await qc.invalidateQueries({ queryKey: ["spot"] });
      await qc.invalidateQueries({ queryKey: ["summary"] });
      await qc.invalidateQueries({ queryKey: ["items"] });
      await qc.invalidateQueries({ queryKey: ["item"] });
      await qc.invalidateQueries({ queryKey: ["me"] });
      setSaved(true);
    });
  };

  return (
    <section className="panel" id="prices">
      <h2>Spot prices</h2>
      <p className="muted">How often prices are fetched and which currency values are shown in.</p>
      {!form.scheduler_running && (
        <p className="notice">Automatic price fetching isn't running in this process. Prices only update when you press Refresh on the dashboard.</p>
      )}
      <form className="stack-form" onSubmit={save}>
        <label>
          Currency
          <select value={form.base_currency} onChange={(e) => setForm({ ...form, base_currency: e.target.value })}>
            {form.currencies.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span className="hint">Changing it fetches prices in the new currency on the next poll. Purchase prices aren't converted.</span>
        </label>
        <label>
          Fetch prices every (minutes)
          <input type="number" min={5} max={1440} inputMode="numeric" value={form.spot_poll_minutes} onChange={(e) => setForm({ ...form, spot_poll_minutes: Number(e.target.value) })} />
        </label>
        <label>
          Call a price stale after (minutes)
          <input type="number" min={5} max={10080} inputMode="numeric" value={form.spot_stale_minutes} onChange={(e) => setForm({ ...form, spot_stale_minutes: Number(e.target.value) })} />
        </label>
        <label className="check">
          <input type="checkbox" checked={form.spot_pause_weekends} onChange={(e) => setForm({ ...form, spot_pause_weekends: e.target.checked })} />
          Pause while markets are closed (Friday 5 pm to Sunday 6 pm New York time)
        </label>
        <button className="primary" disabled={busy}>Save</button>
        {saved && <p className="success" role="status">Saved.</p>}
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

export function Providers() {
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return (
    <section className="panel span-all" id="providers">
      <h2>Data providers</h2>
      <p className="muted">
        Where prices come from. API keys are encrypted before they're stored and are never shown again; only the last four characters are kept
        visible so you can tell which key is saved.
      </p>
      {settings.data && !settings.data.encryption_ready && (
        <p className="error">
          Keys can't be saved: CV_ENCRYPTION_KEY isn't set on the server. Run the update script, which adds one, then restart the service.
        </p>
      )}
      <div className="provider-grid">
        {providers.data?.map((p) => <ProviderCard key={p.key} provider={p} />)}
      </div>
    </section>
  );
}

function statusOf(p: Provider): { cls: string; text: string } {
  if (p.needs_key && !p.key_set) return { cls: "", text: "Not set up" };
  if (!p.enabled) return { cls: "", text: "Turned off" };
  if (p.last_error && (!p.last_success_at || p.last_error_at! > p.last_success_at)) return { cls: "badge-bad", text: "Last call failed" };
  if (p.last_success_at) return { cls: "badge-good", text: "Working" };
  return { cls: "", text: "Not used yet" };
}

function ProviderCard({ provider: p }: { provider: Provider }) {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [replacing, setReplacing] = useState(false);
  const [cap, setCap] = useState(p.quota_cap === null ? "" : String(p.quota_cap));
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const { error, busy, run } = useRun();
  useEffect(() => setCap(p.quota_cap === null ? "" : String(p.quota_cap)), [p.quota_cap]);

  const put = (body: Parameters<typeof api.updateProvider>[1]) =>
    run(async () => {
      const out = await api.updateProvider(p.key, body);
      qc.setQueryData<Provider[]>(["providers"], (old) => old?.map((x) => (x.key === p.key ? out : x)));
    });

  const status = statusOf(p);
  return (
    <article className="provider" aria-labelledby={`prov-${p.key}`}>
      <header className="provider-head">
        <div>
          <h3 id={`prov-${p.key}`}>{p.label}</h3>
          <span className="hint">{p.kind === "spot" ? "Spot prices" : p.kind === "catalog" ? "Coin lookup by cert number" : "Sold prices (comps)"}</span>
        </div>
        <span className={`badge ${status.cls}`}>{status.text}</span>
      </header>
      <p className="provider-note">{p.note}</p>
      <p className="hint">
        <a href={p.docs_url} target="_blank" rel="noreferrer">API documentation</a>
        {p.key_url && <> · <a href={p.key_url} target="_blank" rel="noreferrer">Get a key</a></>}
      </p>

      {p.needs_key && (
        p.key_set && !replacing ? (
          <div className="key-row">
            <span>Key saved, ending <code>{p.key_last4}</code></span>
            <button className="ghost small" onClick={() => setReplacing(true)}>Replace</button>
            <button className="ghost small danger" disabled={busy} onClick={() => { if (window.confirm(`Remove the ${p.label} key?`)) put({ api_key: null }); }}>Remove</button>
          </div>
        ) : (
          <form
            className="inline-form"
            onSubmit={async (e: FormEvent) => {
              e.preventDefault();
              if (await put({ api_key: key.trim() })) {
                setKey("");
                setReplacing(false);
                setResult(null);
              }
            }}
          >
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              aria-label={`${p.label} API key`}
              placeholder="Paste your API key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
            <button className="primary" disabled={busy || !key.trim()}>Save key</button>
            {replacing && <button type="button" className="ghost" onClick={() => setReplacing(false)}>Cancel</button>}
          </form>
        )
      )}

      <div className="provider-controls">
        <label className="check">
          <input type="checkbox" checked={p.enabled} disabled={busy} onChange={(e) => put({ enabled: e.target.checked })} />
          Use this provider
        </label>
        {p.quota_period && (
          <form
            className="cap-form"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              put({ quota_cap: Number(cap) });
            }}
          >
            <label>
              Stop after (requests per {p.quota_period === "calendar_month" ? "month" : p.quota_period === "calendar_day" ? "day" : "billing period"})
              <span className="inline-form">
                <input type="number" min={0} inputMode="numeric" value={cap} onChange={(e) => setCap(e.target.value)} />
                <button className="small" disabled={busy || cap === String(p.quota_cap ?? "")}>Set</button>
              </span>
            </label>
          </form>
        )}
        <button
          className="small"
          disabled={busy || (p.needs_key && !p.key_set)}
          onClick={() =>
            run(async () => {
              const r = await api.testProvider(p.key);
              setResult({ ok: r.ok, message: r.message });
              qc.setQueryData<Provider[]>(["providers"], (old) => old?.map((x) => (x.key === p.key ? r.provider : x)));
              await qc.invalidateQueries({ queryKey: ["provider-usage", p.key] });
              await qc.invalidateQueries({ queryKey: ["provider-calls", p.key] });
            })
          }
        >
          {busy ? "Checking…" : "Test connection"}
        </button>
      </div>
      {result && <p className={result.ok ? "success" : "error"} role="status">{result.message}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {p.usage ? <UsageMeter usage={p.usage} /> : <p className="hint">No request limit to track: this provider is free and keyless.</p>}
      <p className="hint">
        Last worked {ago(p.last_success_at)}.
        {p.last_error && p.last_error_at && <> Last error {ago(p.last_error_at)}: {p.last_error}</>}
      </p>

      <button className="link" onClick={() => setShowHistory((s) => !s)}>{showHistory ? "Hide usage history" : "Show usage history and recent calls"}</button>
      {showHistory && <UsageHistory providerKey={p.key} />}
    </article>
  );
}

/** Requests used against the effective limit (the lower of your cap and the plan's limit). */
export function UsageMeter({ usage: u }: { usage: ProviderUsage }) {
  const limits = [u.cap, u.provider_limit].filter((x): x is number => x !== null && x !== undefined);
  const limit = limits.length ? Math.min(...limits) : null;
  const pct = limit ? Math.min(100, (u.used / limit) * 100) : 0;
  const level = limit === null ? "ok" : u.used >= limit ? "danger" : pct >= 80 ? "warn" : "ok";
  const levelText = level === "danger" ? "Limit reached: calls are paused until it resets." : level === "warn" ? "Over 80% used." : null;
  return (
    <div className="usage">
      <div className="usage-line">
        <span className="tabular">
          <strong>{u.used.toLocaleString()}</strong> {limit !== null ? `of ${limit.toLocaleString()} ` : ""}requests this period
        </span>
        <span className="hint">resets {u.period_end.slice(0, 10) === u.period_start.slice(0, 10) || new Date(u.period_end).getTime() - new Date(u.period_start).getTime() <= 86_400_000 ? "at midnight UTC" : date(u.period_end)}</span>
      </div>
      {limit !== null && (
        <div
          className={`meter meter-${level}`}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuenow={u.used}
          aria-label="Requests used"
        >
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      {levelText && <p className={`meter-note meter-note-${level}`}><span aria-hidden="true">{level === "danger" ? "■" : "▲"}</span> {levelText}</p>}
      <p className="hint">
        Period {date(u.period_start)} to {date(u.period_end)}.
        {u.cap !== null && ` Your cap: ${u.cap.toLocaleString()}.`}
        {u.provider_limit !== null && ` Plan allows ${u.provider_limit.toLocaleString()}.`}
        {u.synced_at ? ` Checked with the provider ${ago(u.synced_at)}.` : " Counted here; not yet checked with the provider."}
      </p>
    </div>
  );
}

function UsageHistory({ providerKey }: { providerKey: string }) {
  const usage = useQuery({ queryKey: ["provider-usage", providerKey], queryFn: () => api.providerUsage(providerKey) });
  const calls = useQuery({ queryKey: ["provider-calls", providerKey], queryFn: () => api.providerCalls(providerKey, 20) });
  const days = (usage.data?.days ?? []).filter((d) => d.calls > 0);
  return (
    <div className="usage-history">
      <h4>By day</h4>
      {days.length === 0 ? (
        <p className="hint">No calls in the last 30 days.</p>
      ) : (
        <table className="figures">
          <thead><tr><th>Day</th><th>Requests counted</th><th>Calls</th><th>Errors</th></tr></thead>
          <tbody>
            {days.slice().reverse().map((d) => (
              <tr key={d.date}><td>{date(d.date + "T12:00:00Z")}</td><td className="tabular">{d.requests}</td><td className="tabular">{d.calls}</td><td className="tabular">{d.errors}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <h4>Recent calls</h4>
      {calls.data?.length ? (
        <table className="figures">
          <thead><tr><th>When</th><th>Call</th><th>Result</th><th>Cost</th></tr></thead>
          <tbody>
            {calls.data.map((c, i) => (
              <tr key={i}>
                <td>{new Date(c.at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}</td>
                <td>{c.endpoint}{c.context ? <span className="hint"> ({c.context})</span> : null}</td>
                <td>{c.status}{c.http_status ? ` ${c.http_status}` : ""}{c.detail ? <span className="hint"> {c.detail}</span> : null}</td>
                <td className="tabular">{c.cost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="hint">No calls yet.</p>
      )}
    </div>
  );
}
