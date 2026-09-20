// Mission Identité — pont Clerk ↔ apiFetch.
//
// apiFetch ( api/base.ts ) lit window.__clerkGetToken : ce
// composant le pose dès que Clerk est monté. Aucune dépendance
// circulaire , un seul endroit injecte le token (§19).
'use client';

import { useEffect } from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';
import { ClerkUserContext } from '../hooks/useCurrentUser';

export function ClerkTokenBridge({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth();
  const clerkUser = useUser();

  useEffect(() => {
    (window as any).__clerkGetToken = getToken;
    return () => {
      delete (window as any).__clerkGetToken;
    };
  }, [getToken]);

  return (
    <ClerkUserContext.Provider value={clerkUser}>
      {children}
    </ClerkUserContext.Provider>
  );
}
