import { test, expect } from '@playwright/test';

// Smoke e2e — une route PUBLIQUE se charge sans crash.
// /sign-in est hors garde de session ( voir App.tsx ) : aucun besoin
// d'auth Neon pour ce test. La spec de démo valide le pipeline complet
// Playwright → webServer vite → rendu React.
test('route publique /sign-in se charge', async ({ page }) => {
  await page.goto('/sign-in');

  // Le titre de la page ( <h1> ) — point d'ancrage stable du layout auth.
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Reprendre une session'
  );

  // Le bouton principal du formulaire — visible quand le formulaire est prêt.
  await expect(
    page.getByRole('button', { name: 'Se connecter' })
  ).toBeVisible();
});