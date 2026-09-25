// Couche API — base fetch + helpers
//
// Mission Identité : TOUTE requête passe par ici → le token
// Clerk ( ou dev ) est injecté UNE fois , ici (§19). Aucun autre
// fichier ne manipule le Authorization header.
import { getDevAuth } from '../auth/devAuth';

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

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const auth = await authHeader();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...auth,
      ...(options?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail =
        typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

/** Variant NON-JSON (SSE texte, etc.) — token injecté pareil. */
export async function apiFetchRaw(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const auth = await authHeader();
  return fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...auth,
      ...(options?.headers ?? {}),
    },
  });
}

export function wsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = BASE ? BASE.replace(/^https?:\/\//, '') : window.location.host;
  return `${proto}://${host}${path}`;
}
