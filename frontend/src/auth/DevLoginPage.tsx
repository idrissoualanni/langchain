// Mission Identité — page de login MODE DEV ( développement
// local sans clés Clerk ). En production : Clerk SignIn.
'use client';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCurrentUser } from '../hooks/useCurrentUser';

export function DevLoginPage() {
  const { devLogin, devMode } = useCurrentUser();
  const [name, setName] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  if (!devMode) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-muted-foreground">
        Mode dev non actif — configurez VITE_AUTH_MODE=dev
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await devLogin(name.trim());
      navigate('/assistant');
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Erreur de connexion');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <form
        onSubmit={submit}
        className="w-80 space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <h1 className="text-lg font-semibold text-slate-100">
          Connexion (dev)
        </h1>
        <p className="text-xs text-slate-400">
          Mode développement : le backend provisionne un utilisateur
          interne de test. En production, l&apos;authentification
          passe par Clerk.
        </p>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nom d'utilisateur"
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600"
        />
        {err && <p className="text-xs text-red-400">{err}</p>}
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="w-full rounded-lg bg-sky-700 px-3 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {busy ? 'Connexion…' : 'Se connecter'}
        </button>
      </form>
    </div>
  );
}
