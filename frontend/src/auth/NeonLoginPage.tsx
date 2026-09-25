// Mission Identité — page de connexion Neon Auth ( production ).
//
// UI maison ( le SDK @neondatabase/auth-ui traîne better-auth@1.6.23
// aux imports circulaires → build cassée ). On utilise le client léger
// src/lib/neon.ts qui parle directement à l'API REST Better Auth.
'use client';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authClient } from '../lib/neon';
import { refreshNeonSession } from './NeonTokenBridge';

export function NeonLoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password || busy) return;
    setBusy(true);
    setErr(null);
    try {
      if (mode === 'sign-up') {
        await authClient.signUpEmail(email.trim(), password, name.trim());
      } else {
        await authClient.signInEmail(email.trim(), password);
      }
      // Rafraîchir le token posé sur window pour apiFetch + l'UI.
      await refreshNeonSession();
      navigate('/assistant', { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Erreur de connexion');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-md space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <div>
          <h1 className="text-lg font-semibold text-slate-100">
            {mode === 'sign-in' ? 'Connexion' : 'Créer un compte'}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            {mode === 'sign-in'
              ? 'Accédez à votre tuteur IA personnel.'
              : 'Inscription à Agent Tutor.'}
          </p>
        </div>

        {mode === 'sign-up' && (
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nom (optionnel)"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600"
          />
        )}

        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Adresse email"
          required
          autoComplete="email"
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600"
        />

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Mot de passe"
          required
          autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
          minLength={8}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-600"
        />

        {err && <p className="text-xs text-red-400">{err}</p>}

        <button
          type="submit"
          disabled={busy || !email.trim() || !password}
          className="w-full rounded-lg bg-sky-700 px-3 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:opacity-50"
        >
          {busy
            ? 'Connexion…'
            : mode === 'sign-in'
              ? 'Se connecter'
              : "S'inscrire"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in');
            setErr(null);
          }}
          className="w-full text-center text-xs text-slate-400 hover:text-slate-200"
        >
          {mode === 'sign-in'
            ? "Pas encore de compte ? S'inscrire"
            : 'Déjà un compte ? Se connecter'}
        </button>
      </form>
    </div>
  );
}
