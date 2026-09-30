// Mission Identité — menu utilisateur Neon Auth ( production ).
//
// Menu utilisateur : avatar + nom + déconnexion via le
// client Neon ( Better Auth managé ). L'identité affichée vient du
// user interne résolu backend ( /api/users/me ).
'use client';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authClient } from '../lib/neon';
import { clearNeonSession } from './NeonTokenBridge';
import { useCurrentUser } from '../hooks/useCurrentUser';

export function NeonUserMenu() {
  const [open, setOpen] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const { internal } = useCurrentUser();
  const navigate = useNavigate();

  const name = internal?.name ?? 'Utilisateur';
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();

  const handleSignOut = async () => {
    setSignOutError(null);
    try {
      await authClient.signOut();
    } catch (err) {
      // ÉCHEC → on ne purge PAS l'état local. Vider l'UI ici ferait
      // croire à une déconnexion alors que le cookie de session Neon
      // est peut-être toujours valide : l'utilisateur verrait son
      // nom et ses droits disparaître, reviendrait sur /sign-in et
      // se retrouverait « connecté » sans comprendre. On le PRÉVIENT
      // et il peut réessayer.
      setSignOutError(
        err instanceof Error
          ? err.message
          : 'Déconnexion impossible — réessaie dans un instant.'
      );
      return;
    }
    // RÉUSSITE → on réaligne l'état global, sinon le header affiche
    // encore l'utilisateur connecté après le logout ( EF-10 ).
    //
    // clearNeonSession() fait les DEUX moitiés indispensables, et
    // SYNSCHRONEMENT : purge du jeton ( window.__neonGetToken + cache
    // JWT — sans quoi le backend continuerait d'accepter l'ancien
    // Bearer jusqu'à son expiration, donc la déconnexion ne serait
    // pas effective) ET publication de l'état vide
    // ( notifyNeonUser(EMPTY) ), qui fait basculer sur-le-champ les
    // gardes Protected / RequireAnonymous.
    //
    // On n'appelle PAS refreshNeonSession() ici : il faudrait attendre
    // un GET /get-session, laissant l'UI « connectée » pendant ce
    // round-trip, et l'ancien Bearer encore attaché à toute requête
    // partie entre-temps.
    clearNeonSession();
    setOpen(false);
    navigate('/sign-in', { replace: true });
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-w-0 items-center gap-2 rounded-md px-1.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        title="Compte"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-700 text-[10px] font-semibold text-slate-100">
          {initials || '?'}
        </span>
        <span className="truncate">{name}</span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-40 rounded-md border border-slate-800 bg-slate-900 py-1 shadow-lg">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              navigate('/profile');
            }}
            className="block w-full px-3 py-1.5 text-left text-xs text-slate-200 hover:bg-slate-800"
          >
            Profil
          </button>
          <button
            type="button"
            onClick={handleSignOut}
            className="block w-full px-3 py-1.5 text-left text-xs text-red-400 hover:bg-slate-800"
          >
            Déconnexion
          </button>
          {/* Une déconnexion ratée doit être VISIBLE : sans ce
              message, le clic semble n'avoir rien fait et
              l'utilisateur réessaie en boucle. */}
          {signOutError && (
            <p className="px-3 py-1.5 text-[11px] leading-snug text-red-300">
              {signOutError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
