// Scénario E2E — route inconnue → page 404 catch-all.
//
// POURQUOI : la route `*` → NotFoundPage est la porte de secours du
// routeur. Si un lien cassé ou une ancienne URL tombe ici, l'utilisateur
// doit avoir des sorties claires vers l'assistant — sinon il est coincé.
import { expect, test } from '@playwright/test';

import { trackConsoleErrors } from './helpers';

test('une URL inconnue affiche la page 404 avec des sorties', async ({
  page,
}) => {
  const errors = trackConsoleErrors(page);

  await page.goto('/chemin/qui/n-existe-pas');

  // Balise texte de la page 404 ( mono, uppercase ).
  await expect(page.getByText('Erreur 404', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    // Apostrophe droite ( ' ) — celle réellement rendue par le composant.
    "Cette page n'existe pas"
  );
  // Sortie principale : retour vers l'assistant.
  await expect(
    page.getByRole('button', { name: "Retour à l'assistant" })
  ).toBeVisible();
  expect(errors).toEqual([]);
});