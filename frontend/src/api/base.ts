// Couche API — base fetch + helpers
//
// Mission Identité : TOUTE requête passe par ici → le token
// Neon ( ou dev ) est injecté UNE fois , ici (§19). Aucun autre
// fichier ne manipule le Authorization header.
//
// Mission Refresh : un 401 n'est plus fatal. Le JWT Neon étant à courte
// durée ( rotation ), une requête peut échouer alors que la session
// sous-jacente est encore valide → on tente un refresh UNE fois, puis on
// réessaie. Évite les déconnexions silencieuses au retour d'onglet.
import { getDevAuth } from '../auth/devAuth';
import { refreshNeonSession } from '../auth/NeonTokenBridge';

const BASE = import.meta.env.VITE_API_URL || '';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Retourne le token d'authentification courant (Neon ou dev). */
async function authHeader(): Promise<Record<string, string>> {
  // Neon Auth ( production ) : token signé Ed25519 posé par
  // NeonTokenBridge, vérifié côté backend via le JWKS Neon.
  const neon = window.__neonGetToken;
  if (neon) {
    try {
      const token = await neon();
      if (token) return { Authorization: `Bearer ${token}` };
    } catch {
      /* pas de session → pas de header */
    }
  }
  const dev = getDevAuth();
  if (dev) return { Authorization: `Bearer ${dev}` };
  return {};
}

/** Rafraîchit la session Neon puis réessaie en cas de 401.
 *
 * NeonTokenBridge n'importe rien de ce module : pas de dépendance
 * circulaire, import statique direct. Les erreurs sont avalées ( une
 * session définitivement morte remonte quand même en ApiError 401 ). */
async function tryRefreshSession(): Promise<void> {
  try {
    await refreshNeonSession();
  } catch {
    /* session définitivement expirée → l'ApiError 401 remonte */
  }
}

/** Étend une réponse d'erreur FastAPI en message lisible. */
async function readErrorDetail(res: Response): Promise<string> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail =
      typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail ?? body);
  } catch {
    /* corps vide → statusText */
  }
  return detail;
}

/** fetch JSON commun ( headers fusionnés : Content-Type puis auth ). */
function fetchJson(
  path: string,
  options: RequestInit | undefined,
  auth: Record<string, string>
): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...auth,
      ...(options?.headers ?? {}),
    },
  });
}

/**
 * Réessaie UNE fois après un 401 si la session vient d'être
 * rafraîchie. Retourne la réponse du retry, ou null si le refresh
 * n'a rien changé ( l'appelant propage alors l'ApiError 401 ).
 *
 * La condition "a-t-on un token après refresh" empêche la boucle
 * infinie : sans session, on ne réessaie pas.
 */
async function retryAfter401(
  path: string,
  options: RequestInit | undefined
): Promise<Response | null> {
  await tryRefreshSession();
  const after = await authHeader();
  // Pas de token après refresh → session réellement morte, on abandonne.
  if (!('Authorization' in after)) return null;
  return fetchJson(path, options, after);
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  let res = await fetchJson(path, options, await authHeader());

  // 401 → refresh + réessai unique ( JWT expiré mais session valide ).
  if (res.status === 401) {
    const retried = await retryAfter401(path, options);
    if (retried) res = retried;
  }

  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }

  return res.json() as Promise<T>;
}

/** Variant NON-JSON (SSE texte, etc.) — token injecté pareil. */
export async function apiFetchRaw(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(await authHeader()),
      ...(options?.headers ?? {}),
    },
  });

  if (res.status === 401) {
    const retried = await retryAfter401(path, options);
    if (retried) return retried;
  }

  return res;
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = BASE ? BASE.replace(/^https?:\/\//, '') : window.location.host;
  return `${proto}://${host}${path}`;
}
