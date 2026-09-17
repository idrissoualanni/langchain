// Mission Identité — garde ADMIN (§9/§20).
// user → 403 UI ; admin → contenu. Le rôle vient de la SESSION
// résolue backend ( /api/users/me ) — jamais déclaré par le
// frontend.
'use client';

import type { ReactNode } from 'react';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { SignedIn, SignedOut, SignIn } from '@clerk/clerk-react';

export function AdminGate({ children }: { children: ReactNode }) {
  const { signedIn, loading, isAdmin, devMode } = useCurrentUser();

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">
        Vérification des droits…
      </div>
    );
  }

  if (!devMode && !signedIn) {
    return (
      <>
        <SignedOut>
          <SignIn routing="hash" />
        </SignedOut>
        <SignedIn>{null}</SignedIn>
      </>
    );
  }
  if (devMode && !signedIn) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">
        Non authentifié ( mode dev )
      </div>
    );
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
