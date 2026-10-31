import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { api, setCsrf } from "./api";
import SpotTicker from "./components/SpotTicker";
import ErrorBoundary from "./ErrorBoundary";
import ThemeToggle from "./components/ThemeToggle";
import Collection from "./pages/Collection";
import Dashboard from "./pages/Dashboard";
import ItemPage from "./pages/ItemPage";
import Login from "./pages/Login";
import NewItem from "./pages/NewItem";
import Settings from "./pages/Settings";
import Photos from "./pages/Photos";
import Report from "./pages/Report";
import Upload from "./pages/Upload";

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

  return (
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
          <NavLink to="/upload">Upload photos</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <SpotTicker />
        <div className="shell-actions">
          <ThemeToggle />
          <button className="signout" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <main className="page">
        <ErrorBoundary resetKey={path}>
        <Routes>
          <Route path="/" element={<Collection />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/items/new" element={<NewItem />} />
          <Route path="/items/:id" element={<ItemPage />} />
          <Route path="/photos" element={<Photos />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/report" element={<Report />} />
          <Route path="/settings" element={<Settings user={me.data.user.username} admin={me.data.user.is_admin} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
