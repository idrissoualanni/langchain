// Mission Identité — hook d'identité : LE user courant.
//
// Source : Clerk ( useUser/useAuth ) en mode clerk ; session dev
// en mode dev. Le user interne ( UUID ) vient de GET /api/users/me
// ( CurrentUserResolver backend ) — le frontend ne CHOISIT plus
// qui il est , il le découvre (§10/§18).
'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiFetch } from '../api/base';
import {
  getDevSession,
  isDevAuthMode,
  setDevSession,
  type DevSession,
} from '../auth/devAuth';

export interface InternalUser {
  user_id: string;
  name: string;
  created_at: string;
  clerk_user_id: string | null;
  role: string;
}

export interface ClerkUserData {
  isLoaded: boolean;
  isSignedIn: boolean | undefined;
  user: any;
}

export const ClerkUserContext = createContext<ClerkUserData>({
  isLoaded: true,
  isSignedIn: false,
  user: null,
});

export function useCurrentUser() {
  const clerkUser = useContext(ClerkUserContext);
  const devMode = isDevAuthMode();

  const [internal, setInternal] = useState<InternalUser | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [devSession, setDevS] = useState<DevSession | null>(() =>
    devMode ? getDevSession() : null
  );

  const signedIn = devMode
    ? devSession !== null
    : clerkUser.isSignedIn === true;

  // Dev : login/logout simulés
  const devLogin = useCallback(
    async (name: string) => {
      const created = await apiFetch<InternalUser & { dev_token?: string }>(
        '/api/users',
        {
          method: 'POST',
          body: JSON.stringify({ name }),
        }
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
    },
    []
  );

  const devLogout = useCallback(() => {
    setDevSession(null);
    setDevS(null);
    setInternal(null);
  }, []);

  // Résolution du user interne depuis la session (Clerk ou dev)
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
  }, [signedIn, devSession?.token]);

  return {
    signedIn,
    loading: devMode ? false : !clerkUser.isLoaded || loading,
    internal,
    role: internal?.role ?? 'user',
    isAdmin: internal?.role === 'admin',
    // Clerk
    clerkUser: devMode ? null : clerkUser.user,
    // Dev
    devMode,
    devLogin,
    devLogout,
  };
}
