// Couche API — base fetch + helpers
//
// Mission Sécurité : PLUS AUCUN header Authorization côté navigateur.
// Le JWT Neon est échangé une fois contre un cookie HttpOnly par
// NeonTokenBridge ( POST /api/auth/session ) ; depuis, chaque requête
// porte `credentials: 'include'` et le navigateur joint le cookie
// tout seul.
//
// Ce n'est pas une optimisation, c'est le but : un header est lisible
// par l'onglet Network, par la console, et par TOUT script injecté dans
// la page. Un XSS n'avait qu'à appeler `window.__neonGetToken()` pour
// voler quinze minutes de session. Le cookie HttpOnly n'est pas
// atteignable depuis le JavaScript de la page — un XSS peut seulement
// faire passer des requêtes au nom de l'utilisateur, pas s'en emparer.
//
// Seul vestige : `getDevAuth()`, qui reste en mode dev local (aucun
// cookie à ce jour, pas de fournisseur d'identité derrière).
//
// Mission Refresh : un 401 n'est plus fatal. Le cookie de session
// suit la durée de vie du JWT (15 min) et est renouvelé en silence par
// NeonTokenBridge ; une requête peut néanmoins tomber pendant ce
// renouvellement → on tente un refresh UNE fois, puis on réessaie.
// Évite les déconnexions silencieuses au retour d'onglet.
import { getDevAuth } from '../auth/devAuth';
import { getNeonUser, refreshNeonSession } from '../auth/NeonTokenBridge';

const BASE = import.meta.env.VITE_API_URL || '';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Retourne le token d'authentification courant.
 *
 * En production : RIEN. Le cookie HttpOnly fait le travail et n'a pas
 * à être lu ici — c'est précisément l'intérêt. Ce helper ne reste que
 * pour le mode dev local (`Bearer dev:<name>`), qui n'a pas de cookie. */
function authHeader(): Record<string, string> {
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

/** fetch JSON commun ( headers fusionnés : Content-Type puis auth ).
 *
 * `credentials: 'include'` est INDISPENSABLE : sans lui le navigateur
 * n'envoie aucun cookie vers une autre origine (notre API est sur
 * `*.onrender.com`, le front sur `*.vercel.app`). C'est le setting qui
 * fait tenir tout le dispositif — et il se trouve ici, une seule fois,
 * plutôt que rappelé à chaque appel. */
function fetchJson(
  path: string,
  options: RequestInit | undefined,
  auth: Record<string, string>
): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    credentials: 'include',
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
 * La condition « la session existe-t-elle encore après refresh ? »
 * empêche la boucle infinie ET la course : `refreshNeonSession()`
 * attend le re-posage du cookie avant de résoudre, donc le retry part
 * avec un cookie à jour. Sans cet `await`, on renverrait la requête
 * avec le cookie expiré et on obtiendrait un second 401.
 */
async function retryAfter401(
  path: string,
  options: RequestInit | undefined
): Promise<Response | null> {
  await tryRefreshSession();
  // Session réellement morte → on abandonne, le 401 remonte.
  if (!getNeonUser().isSignedIn && !getDevAuth()) return null;
  return fetchJson(path, options, authHeader());
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  let res = await fetchJson(path, options, authHeader());

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

/** Variant NON-JSON (SSE texte, etc.) — cookie transmis pareil. */
export async function apiFetchRaw(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      ...authHeader(),
      ...(options?.headers ?? {}),
    },
  });

  if (res.status === 401) {
    const retried = await retryAfter401(path, options);
    if (retried) return retried;
  }

  return res;
}
