// Mission Identité — hook d'identité : LE user courant.
//
// Source : session Neon Auth ( useNeonAuth ) en production ; session dev
// en mode dev. Le user interne ( UUID ) vient de GET /api/users/me
// ( CurrentUserResolver backend ) — le frontend ne CHOISIT plus qui il
// est, il le découvre ( §10/§18 ).
'use client';

import { createContext, useCallback, useEffect, useState } from 'react';
import { ApiError, apiFetch } from '../api/base';
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
  /** Claim `sub` émis par le fournisseur d'identité (Neon Auth).
   *  Nom renamed depuis clerk_user_id : plus aucun Clerk en amont. */
  external_user_id: string | null;
  role: string;
}

export interface NeonUserData {
  isSignedIn: boolean;
  userId: string | null;
  name: string | null;
  email: string | null;
  /** true dès que l'email a été vérifié côté Better Auth.
   *  Pilotage de la bannière "vérifie ta boîte mail". */
  emailVerified: boolean;
  /** true TANT QUE la session n'est pas résolue ( EF-11 ).
   *
   *  Indispensable pour distinguer « pas encore de réponse » de
   *  « déconnecté » : sans cet état, une garde de route lisant
   *  isSignedIn=false avant le premier GET /get-session redirige
   *  vers /sign-in, puis renvoie vers l'app quand la session
   *  arrive — la double redirection à froid. Pendant `pending`, on
   *  n'affiche NI contenu connecté NI redirection. */
  pending: boolean;
}

// Contexte alimenté par NeonTokenBridge pour les composants qui lisent
// l'état d'auth sans se réabonner au client. En pratique, utiliser
// useNeonSession() ( réactif via useSyncExternalStore ).
export const NeonUserContext = createContext<NeonUserData>({
  isSignedIn: false,
  userId: null,
  name: null,
  email: null,
  emailVerified: false,
  // Sans provider, on ne SAIT rien : on vaut « en cours de
  // résolution » plutôt que « déconnecté », pour ne pas déclencher
  // une redirection sur une simple absence de provider.
  pending: true,
});

/** Délai maximal d'attente de GET /api/users/me avant de basculer en
 *  ERREUR. fetch n'a pas de timeout natif : sans borne, un cold start
 *  Render lent (~45 s observés) — ou un réseau noir — laissait l'UI
 *  en chargement éternel, sans rien dire. 30 s au-delà desquels on
 *  préfère afficher une erreur explicite à un spinner infini. */
const ME_TIMEOUT_MS = 30_000;

/** Traduit l'échec de /api/users/me en message UTILISABLE.
 *
 *  Le point important est de ne jamais présenter un échec technique
 *  comme une absence de droits : c'est ce qui produisait le
 *  downgrade silencieux. Ici on distingue explicitement le délai
 *  dépassé, le refus de la session, et la panne serveur/réseau. */
function describeMeError(err: unknown): string {
  // AbortError = notre propre AbortController ( timeout ou cleanup ).
  if (err instanceof DOMException && err.name === 'AbortError') {
    return `Vérification de la session abandonnée après ${ME_TIMEOUT_MS / 1000} s — le serveur ne répond pas.`;
  }
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return "Session refusée par le serveur (401) — reconnecte-toi pour continuer.";
    }
    return `Le serveur n'a pas pu confirmer ta session (erreur ${err.status}).`;
  }
  if (err instanceof TypeError) {
    return 'Impossible de joindre le serveur — vérifie ta connexion.';
  }
  return 'Impossible de vérifier ta session — réessaie dans un instant.';
}

export function useCurrentUser() {
  const neonUser = useNeonSession();
  const devMode = isDevAuthMode();

  const [internal, setInternal] = useState<InternalUser | null>(null);
  const [loading, setLoading] = useState(true);
  // EF-15 : l'échec est un ÉTAT À PART ENTIER, pas un internal=null
  // silencieux. Sans lui, une panne réseau se traduisait par
  // `role ?? 'user'` : l'utilisateur était rétrogradé en « simple
  // utilisateur » sans qu'on lui dise que sa session n'avait pas pu
  // être vérifiée (et l'admin se faisait 403 sur ses propres pages).
  const [error, setError] = useState<string | null>(null);
  // Permet à l'UI de relancer /api/users/me sans recharger l'onglet.
  const [reloadNonce, setReloadNonce] = useState(0);
  const [devSession, setDevS] = useState<DevSession | null>(() =>
    devMode ? getDevSession() : null
  );

  const signedIn = devMode
    ? devSession !== null
    : neonUser.isSignedIn === true;

  // EF-11 : en mode dev la session est SYNCHRONE ( localStorage ), il
  // n'y a donc jamais de résolution en attente. En Neon, au contraire,
  // elle l'est au premier rendu — `signedIn` vaut encore `false` à ce
  // moment-là, ce qui est normal et ne doit déclencher aucune
  // redirection.
  const sessionPending = !devMode && neonUser.pending === true;

  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);

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

  // Résolution du user interne depuis la session ( Neon ou dev ).
  //
  // Trois états distincts et non ambigus :
  //   1. loading → aucune conclusion, on n'affiche rien de définitif
  //   2. internal + error=null → la session est confirmée par le backend
  //   3. error → on N'A PAS PU vérifier ( délai, réseau, 5xx, 401 )
  // L'ancien code faisait 3 ≈ 1 : le `catch` remettait internal à
  // null, indiscernable de « pas de session », et `role ?? 'user'`
  // downgradeait silencieusement.
  useEffect(() => {
    let alive = true;
    if (!signedIn) {
      setInternal(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    // EF-19 : fetch n'a pas de timeout → on en pose un. Le signal est
    // aussi indispensable pour ANNULER la requête si l'effet est
    // rejoué (changement d'utilisateur) — sinon la réponse tardive
    // d'une session abandonnée écrasait la nouvelle.
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), ME_TIMEOUT_MS);

    apiFetch<InternalUser>('/api/users/me', { signal: controller.signal })
      .then((u) => {
        if (alive) setInternal(u);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setInternal(null);
        setError(describeMeError(err));
      })
      .finally(() => {
        window.clearTimeout(timer);
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [signedIn, neonUser.userId, devSession?.token, reloadNonce]);

  return {
    signedIn,
    loading,
    internal,
    // Rôle INCONNU tant que le backend n'a pas répondu. Avant :
    // `internal?.role ?? 'user'` — un simple `??` ne distingue pas
    // « rôle absent » de « résolution échouée », et transformait toute
    // panne en compte sans droits. `null` = inconnu, pas « user ».
    role: internal?.role ?? null,
    isAdmin: internal?.role === 'admin',
    error,
    reload,
    sessionPending,
    neonUser: devMode ? null : neonUser,
    devMode,
    devLogin,
    devLogout,
  };
}
