// Mission Identité — menu utilisateur Neon Auth ( production ).
//
// Remplace le UserButton Clerk : avatar + nom + déconnexion via le
// client Neon ( Better Auth managé ). L'identité affichée vient du
// user interne résolu backend ( /api/users/me ).
'use client';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authClient } from '../lib/neon';
import { useCurrentUser } from '../hooks/useCurrentUser';

export function NeonUserMenu() {
  const [open, setOpen] = useState(false);
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
    try {
      await authClient.signOut();
    } catch {
      /* session déjà expirée */
    }
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
        </div>
      )}
    </div>
  );
}
