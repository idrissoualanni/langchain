// Mission Identité — mode dev local ( sans clés Clerk ).
//
// En développement ( VITE_AUTH_MODE=dev ) le backend accepte
// "dev:<internal_user_id>" comme session simulée ( cf
// backend/app/auth/resolver.py ). Ce module gère ce token côté
// frontend : le user se connecte avec un nom , le backend le
// provisionne , le token est stocké en localStorage.
//
// En mode clerk ( production ) ce module est inerte : getDevAuth()
// retourne null et l'auth passe par Clerk.
const DEV_KEY = 'dsh_dev_auth';

export interface DevSession {
  token: string; // "dev:<uuid>"
  user_id: string;
  name: string;
  role: string;
}

export function getDevAuth(): string | null {
  if (import.meta.env.VITE_AUTH_MODE !== 'dev') return null;
  try {
    const raw = localStorage.getItem(DEV_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as DevSession;
    return s?.token ?? null;
  } catch {
    return null;
  }
}

export function getDevSession(): DevSession | null {
  if (import.meta.env.VITE_AUTH_MODE !== 'dev') return null;
  try {
    const raw = localStorage.getItem(DEV_KEY);
    return raw ? (JSON.parse(raw) as DevSession) : null;
  } catch {
    return null;
  }
}

export function setDevSession(s: DevSession | null): void {
  if (s) localStorage.setItem(DEV_KEY, JSON.stringify(s));
  else localStorage.removeItem(DEV_KEY);
}

export function isDevAuthMode(): boolean {
  return import.meta.env.VITE_AUTH_MODE === 'dev';
}
