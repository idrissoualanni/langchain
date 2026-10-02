// Helper partagé entre les specs E2E Playwright.
// Ce fichier n'est PAS collecté comme test : seul un suffixe .spec.{ts,tsx}
// est exécuté par playwright ( testDir: './e2e' dans playwright.config.ts ).
import { readFileSync } from 'node:fs';

import type { Page } from '@playwright/test';

/**
 * Enregistre toutes les erreurs console ( type === 'error' ) émises par la
 * page pendant un test.
 *
 * POURQUOI : un crash React ( « h1 fantôme » de page blanche ) ou une
 * ressource cassée se manifeste toujours par une erreur console AVANT
 * même que les assertions de rendu échouent. Tester `expect(errors)`
 * égale à `[]` en fin de scénario détecte les régressions invisibles.
 */
export function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Les échecs de chargement réseau du navigateur ( « Failed to load
      // resource: ... ERR_CONNECTION_REFUSED » ) sont ENVIRONNEMENTAUX en
      // E2E : sans backend sur :8000, l'app tente l'API et échoue au
      // niveau réseau — ce n'est pas un bug applicatif. On ne retient
      // que les erreurs console réelles ( exceptions JS, 404 applicatifs ).
      if (/Failed to load resource/.test(text)) return;
      errors.push(text);
    }
  });
  return errors;
}

/**
 * Lit VITE_NEON_AUTH_URL / VITE_API_URL depuis frontend/.env.
 *
 * POURQUOI : les mocks de session ( spec documents ) doivent
 * intercepter les MÊMES URLs que l'application résout à
 * l'import ( import.meta.env au build Vite ). Dupliquer les URLs en
 * dur dans les specs les ferait diverger silencieusement du .env —
 * on le parse donc à la source.
 */
export function loadFrontendEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  try {
    const raw = readFileSync(new URL('../.env', import.meta.url), 'utf-8');
    for (const line of raw.split(/\r?\n/)) {
      const m = /^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$/.exec(line);
      if (m && !line.trimStart().startsWith('#')) env[m[1]] = m[2];
    }
  } catch {
    /* .env absent : les specs utilisent leurs valeurs de repli */
  }
  return env;
}

/**
 * JWT factice dont SEUL le payload `exp` est significatif.
 *
 * NeonTokenBridge.decodeExp décode la 2e partie base64 pour connaître
 * l'échéance — côté navigateur, la signature n'est JAMAIS vérifiée
 * ( c'est le travail du backend ). Un JWT signé est donc inutile en
 * E2E : le test mocke aussi POST /api/auth/session.
 */
export function makeFakeJwt(ttlSeconds: number): string {
  const payload = Buffer.from(
    JSON.stringify({
      sub: 'neon-e2e',
      exp: Math.floor(Date.now() / 1000) + ttlSeconds,
    })
  ).toString('base64');
  return `e2e.${payload}.not-a-signature`;
}