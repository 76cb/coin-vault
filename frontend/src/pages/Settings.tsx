import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { api, ApiToken } from "../api";
import Backups from "../components/Backups";
import ValueUpdates from "../components/ValueUpdates";
import { PriceSettings, Providers } from "../components/Providers";
import { useThemeChoice } from "../components/ThemeToggle";
import { getPhotoFit, PhotoFit, setPhotoFit, ThemeChoice } from "../theme";

const SCOPES: [string, string][] = [
  ["items:read", "Read items"],
  ["items:write", "Change items"],
  ["prices:read", "Read prices"],
  ["export", "Export data"],
];

export default function Settings({ user, admin }: { user: string; admin: boolean }) {
  return (
    <>
      <div className="page-head">
        <h1>Settings</h1>
      </div>
      <div className="settings">
        <Appearance />
        <PriceSettings />
        <Providers />
        <Locations />
        <Tags />
        {admin && <ValueUpdates />}
        {admin && <Backups />}
        <Tokens />
        <Password user={user} />
      </div>
    </>
  );
}

function Appearance() {
  const [choice, set] = useThemeChoice();
  const [fit, setFit] = useState<PhotoFit>(getPhotoFit);
  const options: [ThemeChoice, string][] = [
    ["system", "Same as device"],
    ["light", "Light"],
    ["dark", "Dark"],
  ];
  return (
    <section className="panel">
      <h2>Appearance</h2>
      <div className="segmented" role="radiogroup" aria-label="Theme">
        {options.map(([v, label]) => (
          <button key={v} type="button" role="radio" aria-checked={choice === v} className={choice === v ? "on" : ""} onClick={() => set(v)}>
            {label}
          </button>
        ))}
      </div>
      <p className="hint">Remembered in this browser. The moon or sun button in the header switches too.</p>
      <h3 className="sub-h">Photos in the collection</h3>
      <div className="segmented" role="radiogroup" aria-label="Photos in the collection">
        {([["fill", "Fill the tile"], ["whole", "Show the whole photo"]] as [PhotoFit, string][]).map(([v, label]) => (
          <button key={v} type="button" role="radio" aria-checked={fit === v} className={fit === v ? "on" : ""} onClick={() => { setPhotoFit(v); setFit(v); }}>
            {label}
          </button>
        ))}
      </div>
      <p className="hint">Fill crops the edges to make a neat grid. To choose exactly what shows, open the item and use Edit on the photo (Square crop).</p>
    </section>
  );
}

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

function Locations() {
  const qc = useQueryClient();
  const locs = useQuery({ queryKey: ["locations"], queryFn: api.locations });
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const { error, busy, run } = useRun();
  const refresh = () => qc.invalidateQueries({ queryKey: ["locations"] });

  return (
    <section className="panel">
      <h2>Storage locations</h2>
      <p className="muted">Nest them the way you store things, such as Safe, then Drawer 2, then Box A.</p>
      <ul className="plain-list">
        {locs.data?.map((l) => (
          <li key={l.id}>
            <span>{l.path}</span>
            <span className="hint">{l.item_count} item{l.item_count === 1 ? "" : "s"}</span>
            <button
              className="ghost small danger"
              disabled={busy}
              onClick={() => run(async () => { await api.deleteLocation(l.id); await refresh(); })}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form
        className="inline-form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          run(async () => {
            await api.createLocation(name.trim(), parent ? Number(parent) : null);
            setName("");
            await refresh();
          });
        }}
      >
        <input aria-label="New location name" placeholder="New location" value={name} onChange={(e) => setName(e.target.value)} required />
        <select aria-label="Inside" value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">At the top level</option>
          {locs.data?.map((l) => <option key={l.id} value={l.id}>Inside {l.path}</option>)}
        </select>
        <button className="primary" disabled={busy || !name.trim()}>Add location</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Tags() {
  const qc = useQueryClient();
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const { error, busy, run } = useRun();
  if (!tags.data?.length) return null;
  return (
    <section className="panel">
      <h2>Tags</h2>
      <ul className="plain-list">
        {tags.data.map((t) => (
          <li key={t.id}>
            <span>{t.name}</span>
            <span className="hint">{t.item_count} item{t.item_count === 1 ? "" : "s"}</span>
            <button
              className="ghost small"
              disabled={busy}
              onClick={() => {
                const name = window.prompt("Rename tag", t.name);
                if (name && name.trim() !== t.name) run(async () => { await api.renameTag(t.id, name.trim()); await qc.invalidateQueries({ queryKey: ["tags"] }); });
              }}
            >
              Rename
            </button>
            <button className="ghost small danger" disabled={busy} onClick={() => run(async () => { await api.deleteTag(t.id); await qc.invalidateQueries({ queryKey: ["tags"] }); })}>
              Delete
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Tokens() {
  const qc = useQueryClient();
  const tokens = useQuery({ queryKey: ["tokens"], queryFn: api.tokens });
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["items:read"]);
  const [days, setDays] = useState("365");
  const [created, setCreated] = useState<ApiToken | null>(null);
  const { error, busy, run } = useRun();
  const refresh = () => qc.invalidateQueries({ queryKey: ["tokens"] });

  return (
    <section className="panel">
      <h2>API tokens</h2>
      <p className="muted">For scripts and other tools on your network. Each token can only do what you tick.</p>
      {created?.token && (
        <div className="notice" role="status">
          <p>Copy this token now. It won't be shown again.</p>
          <code className="token-value">{created.token}</code>
          <button className="ghost small" onClick={() => navigator.clipboard?.writeText(created.token!)}>Copy</button>
        </div>
      )}
      <ul className="plain-list">
        {tokens.data?.map((t) => (
          <li key={t.id} className={t.revoked_at ? "revoked" : ""}>
            <span>{t.name} <code>cv_{t.prefix}_…</code></span>
            <span className="hint">
              {t.scopes.join(", ")}
              {t.revoked_at ? "; revoked" : t.expires_at ? `; expires ${new Date(t.expires_at).toLocaleDateString()}` : ""}
              {t.last_used_at ? `; last used ${new Date(t.last_used_at).toLocaleDateString()}` : "; never used"}
            </span>
            {!t.revoked_at && (
              <button className="ghost small danger" disabled={busy} onClick={() => run(async () => { await api.revokeToken(t.id); await refresh(); })}>
                Revoke
              </button>
            )}
          </li>
        ))}
      </ul>
      <form
        className="stack-form"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          run(async () => {
            setCreated(await api.createToken(name.trim(), scopes, days ? Number(days) : null));
            setName("");
            await refresh();
          });
        }}
      >
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Home Assistant" required />
        </label>
        <fieldset className="checks">
          <legend>Allowed to</legend>
          {SCOPES.map(([k, v]) => (
            <label key={k} className="check">
              <input type="checkbox" checked={scopes.includes(k)} onChange={(e) => setScopes((s) => (e.target.checked ? [...s, k] : s.filter((x) => x !== k)))} />
              {v}
            </label>
          ))}
        </fieldset>
        <label>
          Expires after (days)
          <input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} placeholder="Never" />
        </label>
        <button className="primary" disabled={busy || !name.trim() || scopes.length === 0}>Create token</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Password({ user }: { user: string }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [ok, setOk] = useState(false);
  const { error, busy, run } = useRun();
  return (
    <section className="panel">
      <h2>Password</h2>
      <p className="muted">Signed in as {user}. Changing the password signs out your other browsers.</p>
      <form
        className="stack-form"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setOk(false);
          if (await run(() => api.changePassword(current, next))) {
            setCurrent("");
            setNext("");
            setOk(true);
          }
        }}
      >
        <input type="text" autoComplete="username" value={user} readOnly hidden />
        <label>
          Current password
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </label>
        <label>
          New password
          <input type="password" autoComplete="new-password" minLength={10} value={next} onChange={(e) => setNext(e.target.value)} required />
          <span className="hint">At least 10 characters.</span>
        </label>
        <button className="primary" disabled={busy}>Change password</button>
        {ok && <p className="success" role="status">Password changed.</p>}
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
