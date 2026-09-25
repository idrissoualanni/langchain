// Mission Identité — client Neon Managed Better Auth ( version légère ).
//
// Le SDK @neondatabase/auth traîne better-auth@1.6.23 qui contient des
// imports circulaires internes ( client/index.mjs → lui-même ) que
// rolldown refuse de bundler ( 33 erreurs à la build ).
//
// On parle donc directement à l'API REST Better Auth du service Neon
// Auth avec fetch — endpoints standards Better Auth v1 :
//   POST /sign-up/email, POST /sign-in/email, GET /get-session,
//   POST /sign-out, GET /.well-known/jwks.json.
// Le cookie de session est géré par le navigateur ( SameSite + credentials ).
//
// Aucune dépendance npm → bundle léger, zero import circulaire.

const AUTH_URL = import.meta.env.VITE_NEON_AUTH_URL as string;

/** Session Better Auth : { user, session, token? }. */
export interface NeonSession {
  session?: { id: string; token?: string; expiresAt?: string };
  user?: {
    id: string;
    name?: string | null;
    email?: string | null;
    image?: string | null;
  };
  token?: string | null;
}

async function postJson(path: string, body: Record<string, unknown>) {
  const res = await fetch(`${AUTH_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(body),
  });
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* réponse vide */
  }
  if (!res.ok) {
    const msg =
      (data as { message?: string })?.message ?? `Erreur ${res.status}`;
    throw new Error(msg);
  }
  return data as NeonSession;
}

async function getJson<T>(path: string): Promise<T | null> {
  const res = await fetch(`${AUTH_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  if (!res.ok) return null;
  try {
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const authClient = {
  /** Inscrit un utilisateur ( email + mot de passe ). */
  signUpEmail: (email: string, password: string, name?: string) =>
    postJson('/sign-up/email', { email, password, name: name ?? '' }),

  /** Connecte un utilisateur ( email + mot de passe ). */
  signInEmail: (email: string, password: string) =>
    postJson('/sign-in/email', { email, password }),

  /** Session courante ( null si déconnecté ). */
  getSession: () => getJson<NeonSession>('/get-session'),

  /** Déconnexion. */
  signOut: () =>
    postJson('/sign-out', {}).catch(() => {
      /* session déjà expirée */
    }),

  /** JWT signé ( Ed25519 ) pour le backend.
   *
   * NB : session.token est un token OPAQUE ( 32 chars, pas un JWT )
   * — inutilisable pour verify_neon_token() côté backend. Better Auth
   * expose le vrai JWT signé sur l'endpoint /token ( getJWTToken ).
   */
  async getJWTToken(): Promise<string | null> {
    const t = await getJson<{ token: string | null }>('/token');
    return t?.token ?? null;
  },
};
