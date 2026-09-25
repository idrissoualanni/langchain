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
    /** Better Auth : true dès que l'email a été vérifié. */
    emailVerified?: boolean | null;
    /** Better Auth : timestamp ( s ) de la dernière vérification. */
    emailVerifiedAt?: number | null;
  };
  token?: string | null;
}

async function postJson(path: string, body: Record<string, unknown>) {
  const res = await fetch(`${AUTH_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Neon exige un header Origin quand callbackURL est relative
      // ( sinon 400 MISSING_ORIGIN ). On envoie l'origine du frontend.
      Origin: window.location.origin,
    },
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

  // ----------------------------------------------------------------
  // Vérification d'email ( Neon = plugin Better Auth "email-otp" )
  // ----------------------------------------------------------------
  // ATTENTION : malgré le choix "Verification link" dans la console,
  // Neon route par les endpoints /email-otp/* du plugin email-otp, et
  // NON par /verify-email ( qui répond 404 ). Le "link" mail contient
  // un code OTP ; on le valide via /email-otp/verify-email avec le
  // champ "otp" ( pas "token" ).

  /** Envoie ( ou renvoie ) l'email de vérification à l'utilisateur
   *  connecté. Répond { status: true } — 200 même si l'envoi SMTP
   *  échoue ( transport non configuré ). */
  sendVerificationEmail: (email: string) =>
    postJson('/send-verification-email', { email }),

  /** Valide le code reçu par email ( plugin email-otp ).
   *  Exige l'email + le code ( validation serveur : les deux champs
   *  sont obligatoires ). Champ "otp" — JAMAIS "token". */
  verifyEmail: (email: string, otp: string) =>
    postJson('/email-otp/verify-email', { email, otp }),

  // ----------------------------------------------------------------
  // Mot de passe oublié — INDISPONIBLE sur ce projet Neon
  // ----------------------------------------------------------------
  // Tests e2e ( 2026-09-25 ) : Neon Managed Auth n'envoie QUE des
  // emails de vérification. /send-verification-email répond 200 à tous
  // les "type" tentés ( forgetPassword / resetPassword / password ),
  // mais AUCUN email de réinitialisation n'arrive ( vérifié en boîte
  // jetable ). /reset-password standard exige un token qui n'est jamais
  // envoyé, et /email-otp/reset-password rejette les OTP de vérification
  // ( INVALID_OTP ).
  //
  // Tant que Neon n'expose pas de flux de réinitialisation, on désactive
  // ces méthodes côté client : elles renvoient une erreur explicite
  // plutôt que de laisser l'utilisateur attendre un email qui ne vient
  // jamais.

  /** Demande de réinitialisation — NON SUPPORTÉE par Neon.
   *  Lève systématiquement pour que l'UI propose la marche à suivre. */
  forgetPassword: async (_email: string): Promise<never> => {
    throw new Error(
      'RESET_UNAVAILABLE: la réinitialisation de mot de passe n\'est pas activée sur ce projet Neon. Contactez un administrateur.'
    );
  },

  /** Réinitialisation — NON SUPPORTÉE par Neon. */
  resetPassword: async (
    _token: string,
    _password: string
  ): Promise<never> => {
    throw new Error(
      'RESET_UNAVAILABLE: la réinitialisation de mot de passe n\'est pas activée sur ce projet Neon.'
    );
  },
};
