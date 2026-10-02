// Scénarios E2E — pages d'authentification publiques.
//
// POURQUOI ces routes-là : ce sont les seules testables SANS backend ni
// session ( aucune dépendance API ). VITE_AUTH_MODE=neon en dev ( .env )
// ⇒ devMode=false ⇒ la garde RequireAuth renvoie vers /sign-in, donc
// aucune page protégée n'est atteignable sans vraie authentification.
// On vérifie ici que chaque page se charge avec son h1 exact et sans
// erreur console — un crash React ou une URL cassée serait vu
// immédiatement.
import { expect, test } from '@playwright/test';

import { trackConsoleErrors } from './helpers';

test.describe('Pages d’authentification publiques', () => {
  // Boucle sur les pages publiques du layout auth : titre h1 exact +
  // titre du document + zéro erreur console.
  for (const { path, h1 } of [
    { path: '/sign-in', h1: 'Reprendre une session' },
    { path: '/sign-up', h1: 'Créer un compte' },
    { path: '/forgot-password', h1: 'Mot de passe oublié' },
  ] as const) {
    test(`${path} se charge avec son h1 et sans erreur`, async ({ page }) => {
      const errors = trackConsoleErrors(page);

      await page.goto(path);

      await expect(page.getByRole('heading', { level: 1 })).toHaveText(h1);
      // toHaveTitle fait une correspondance partielle : le document partage
      // un titre unique ( index.html ) pour toutes les pages SPA.
      await expect(page).toHaveTitle('Agent Lab — Control Center');
      expect(errors).toEqual([]);
    });
  }

  test('/dev-login reste inerte hors mode dev (garde de sécurité)', async ({
    page,
  }) => {
    const errors = trackConsoleErrors(page);

    await page.goto('/dev-login');

    // devMode=false ( VITE_AUTH_MODE=neon ) : la page ne doit PAS proposer
    // la simulation de session — elle affiche son état désactivé.
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      'Mode développement désactivé'
    );
    expect(errors).toEqual([]);
  });
});