// Mission Identité — hook d'identité : LE user courant.
//
// Source : session Neon Auth ( useNeonAuth ) en production ; session dev
// en mode dev. Le user interne ( UUID ) vient de GET /api/users/me
// ( CurrentUserResolver backend ) — le frontend ne CHOISIT plus qui il
// est, il le découvre ( §10/§18 ).
'use client';

import { createContext, useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/base';
import {
  getDevSession,
  isDevAuthMode,
  setDevSession,
  type DevSession,
} from '../auth/devAuth';
import { useNeonSession } from './useNeonSession';

export interface InternalUser {
  user_id: string;
  name: string;
  created_at: string;
  clerk_user_id: string | null;
  role: string;
}

export interface NeonUserData {
  isSignedIn: boolean;
  userId: string | null;
  name: string | null;
  email: string | null;
}

// Contexte alimenté par NeonTokenBridge pour les composants qui lisent
// l'état d'auth sans se réabonner au client. En pratique, utiliser
// useNeonSession() ( réactif via useSyncExternalStore ).
export const NeonUserContext = createContext<NeonUserData>({
  isSignedIn: false,
  userId: null,
  name: null,
  email: null,
});

export function useCurrentUser() {
  const neonUser = useNeonSession();
  const devMode = isDevAuthMode();

  const [internal, setInternal] = useState<InternalUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [devSession, setDevS] = useState<DevSession | null>(() =>
    devMode ? getDevSession() : null
  );

  const signedIn = devMode
    ? devSession !== null
    : neonUser.isSignedIn === true;

  // Dev : login/logout simulés ( mode dev local uniquement )
  const devLogin = useCallback(async (name: string) => {
    const created = await apiFetch<InternalUser & { dev_token?: string }>(
      '/api/users',
      { method: 'POST', body: JSON.stringify({ name }) }
    );
    if (!created.dev_token) throw new Error('Mode dev requis côté backend');
    const s: DevSession = {
      token: created.dev_token,
      user_id: created.user_id,
      name: created.name,
      role: created.role,
    };
    setDevSession(s);
    setDevS(s);
    setInternal(created);
    return created;
  }, []);

  const devLogout = useCallback(() => {
    setDevSession(null);
    setDevS(null);
    setInternal(null);
  }, []);

  // Résolution du user interne depuis la session ( Neon ou dev )
  useEffect(() => {
    let alive = true;
    if (!signedIn) {
      setInternal(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    apiFetch<InternalUser>('/api/users/me')
      .then((u) => {
        if (alive) setInternal(u);
      })
      .catch(() => {
        if (alive) setInternal(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [signedIn, neonUser.userId, devSession?.token]);

  return {
    signedIn,
    loading,
    internal,
    role: internal?.role ?? 'user',
    isAdmin: internal?.role === 'admin',
    neonUser: devMode ? null : neonUser,
    devMode,
    devLogin,
    devLogout,
  };
}
