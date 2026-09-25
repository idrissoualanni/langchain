// Mission Identité — garde ADMIN ( §9/§20 ).
// user → 403 UI ; admin → contenu. Le rôle vient de la SESSION
// résolue backend ( /api/users/me ) — jamais déclaré par le frontend.
'use client';

import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useCurrentUser } from '../hooks/useCurrentUser';

export function AdminGate({ children }: { children: ReactNode }) {
  const { signedIn, loading, isAdmin, devMode } = useCurrentUser();

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">
        Vérification des droits…
      </div>
    );
  }

  // Pas de session → page de connexion ( Neon en prod, dev-login en dev ).
  if (!signedIn) {
    return <Navigate to={devMode ? '/dev-login' : '/sign-in'} replace />;
  }

  if (!isAdmin) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-slate-400">
        <span className="text-2xl">🔒</span>
        <span>Accès réservé aux administrateurs.</span>
      </div>
    );
  }

  return <>{children}</>;
}
