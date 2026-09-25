// Mission Identité — pont Neon Auth ↔ apiFetch + contexte user réactif.
//
// apiFetch ( api/base.ts ) lit window.__neonGetToken : ce module le
// pose dès qu'une session Neon existe. Un seul endroit injecte le
// token ( §19 ) — aucun autre fichier ne touche au header Authorization.
// Il alimente aussi NeonUserContext ( nom/email pour les pages profil ).
//
// État partagé entre instances ( la page de login déclenche le refresh,
// Protected et la sidebar s'y abonnent ).
'use client';

import { useEffect, useState } from 'react';
import { authClient } from '../lib/neon';
import { NeonUserContext, type NeonUserData } from '../hooks/useCurrentUser';

const EMPTY: NeonUserData = {
  isSignedIn: false,
  userId: null,
  name: null,
  email: null,
};

let currentUser: NeonUserData = EMPTY;
let listeners: Array<(u: NeonUserData) => void> = [];

export function notifyNeonUser(u: NeonUserData) {
  currentUser = u;
  listeners.forEach((fn) => fn(u));
}

export function getNeonUser(): NeonUserData {
  return currentUser;
}

export function subscribeNeonUser(
  fn: (u: NeonUserData) => void
): () => void {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((f) => f !== fn);
  };
}

/** Rafraîchit le token + l'user ( login / focus / retour d'onglet ). */
export async function refreshNeonSession() {
  try {
    const session = await authClient.getSession();
    const token = session?.token ?? session?.session?.token ?? null;

    (window as any).__neonGetToken =
      token != null ? () => Promise.resolve(token) : undefined;

    notifyNeonUser({
      isSignedIn: !!session?.user,
      userId: session?.user?.id ?? null,
      name: session?.user?.name ?? null,
      email: session?.user?.email ?? null,
    });
  } catch {
    (window as any).__neonGetToken = undefined;
    notifyNeonUser(EMPTY);
  }
}

export function NeonTokenBridge({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<NeonUserData>(currentUser);

  useEffect(() => {
    const unsub = subscribeNeonUser(setUser);
    // Premier chargement : résoudre la session existante.
    refreshNeonSession();
    // Rafraîchir au retour sur l'onglet ( session peut expirer ).
    window.addEventListener('focus', refreshNeonSession);
    return () => {
      unsub();
      window.removeEventListener('focus', refreshNeonSession);
    };
  }, []);

  return (
    <NeonUserContext.Provider value={user}>
      {children}
    </NeonUserContext.Provider>
  );
}
