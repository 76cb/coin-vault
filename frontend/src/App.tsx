import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { CanWrite } from "./access";
import { api, METAL_LABELS, money, setCsrf } from "./api";
import SpotTicker from "./components/SpotTicker";
import ErrorBoundary from "./ErrorBoundary";
import ThemeToggle from "./components/ThemeToggle";
import Collection from "./pages/Collection";
import Dashboard from "./pages/Dashboard";
import Goldbacks from "./pages/Goldbacks";
import ItemPage from "./pages/ItemPage";
import Login from "./pages/Login";
import NewItem from "./pages/NewItem";
import Settings from "./pages/Settings";
import Photos from "./pages/Photos";
import Report from "./pages/Report";
import Upload from "./pages/Upload";
import { Alerts, Checklists, ImportCsv, InventoryCheck, Labels, Sales, Tools, Wants } from "./pages/Tools";

export default function App() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: Infinity });
  const path = useLocation().pathname;

  useEffect(() => {
    setCsrf(me.data?.csrf_token ?? null);
  }, [me.data]);

  useEffect(() => {
    const onOut = () => qc.setQueryData(["me"], null);
    window.addEventListener("cv:signed-out", onOut);
    return () => window.removeEventListener("cv:signed-out", onOut);
  }, [qc]);

  if (me.isPending) return <div className="boot" aria-busy="true" />;
  if (!me.data) return <Login onSignedIn={(m) => { setCsrf(m.csrf_token); qc.setQueryData(["me"], m); }} />;

  const signOut = async () => {
    try {
      await api.logout();
    } finally {
      qc.clear();
      qc.setQueryData(["me"], null);
    }
  };

  const canWrite = !me.data.read_only;

  return (
    <CanWrite.Provider value={canWrite}>
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="Coin Vault home">
          <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
            <circle cx="16" cy="16" r="12" fill="none" stroke="currentColor" strokeWidth="2.5" />
            <circle cx="16" cy="16" r="7" fill="none" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          Coin Vault
        </NavLink>
        <nav className="mainnav">
          <NavLink to="/" end>Collection</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/photos">Photos</NavLink>
          <NavLink to="/goldbacks">Goldbacks</NavLink>
          {canWrite && <NavLink to="/upload">Upload photos</NavLink>}
          <NavLink to="/tools">Tools</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <SpotTicker />
        <div className="shell-actions">
          <ThemeToggle />
          <button className="signout" onClick={signOut}>Sign out</button>
        </div>
      </header>
      {!canWrite && <p className="readonly-bar" role="status">Read-only login: you can look at everything and change nothing.</p>}
      <FiredAlerts canWrite={canWrite} />
      <main className="page">
        <ErrorBoundary resetKey={path}>
        <Routes>
          <Route path="/" element={<Collection />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/items/new" element={<NewItem />} />
          <Route path="/items/:id" element={<ItemPage />} />
          <Route path="/photos" element={<Photos />} />
          <Route path="/goldbacks" element={<Goldbacks />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/report" element={<Report />} />
          <Route path="/tools" element={<Tools />} />
          <Route path="/checklists" element={<Checklists />} />
          <Route path="/wants" element={<Wants />} />
          <Route path="/sales" element={<Sales />} />
          <Route path="/inventory-check" element={<InventoryCheck />} />
          <Route path="/labels" element={<Labels />} />
          <Route path="/import" element={<ImportCsv />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings user={me.data.user.username} admin={me.data.user.is_admin} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </ErrorBoundary>
      </main>
    </div>
    </CanWrite.Provider>
  );
}

/** Price alerts that have fired and not been dismissed, shown on every page until they are. */
function FiredAlerts({ canWrite }: { canWrite: boolean }) {
  const qc = useQueryClient();
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: api.alerts, refetchInterval: 120_000 });
  const fired = (alerts.data ?? []).filter((a) => a.triggered_at && !a.dismissed_at);
  if (!fired.length) return null;
  return (
    <div className="alert-bar" role="alert">
      {fired.map((a) => (
        <p key={a.id}>
          <strong>{METAL_LABELS[a.metal]}</strong> went {a.direction} {money(a.price, a.currency)}: it was {money(a.triggered_price, a.currency)} on{" "}
          {new Date(a.triggered_at!).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
          {a.note ? ` (${a.note})` : ""}.{" "}
          {canWrite && <button className="link" onClick={async () => { await api.dismissAlert(a.id); await qc.invalidateQueries({ queryKey: ["alerts"] }); }}>Dismiss</button>}
        </p>
      ))}
    </div>
  );
}
