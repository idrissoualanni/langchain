// Scénario E2E — formulaire de connexion ( comportement UI, sans backend ).
//
// ⚠️ DANGER : ce test ne soumet JAMAIS le formulaire. Le submit de
// /sign-in POST vers VITE_NEON_AUTH_URL ( endpoint public Neon ) et
// pourrait créer une vraie session — effet de bord externe interdit
// dans un test. On vérifie uniquement l'état du formulaire :
//   - bouton désactivé tant que les champs sont vides,
//   - activation au remplissage,
//   - toggle de visibilité du mot de passe,
//   - aucune navigation sauvage vers le backend.
import { expect, test } from '@playwright/test';

import { trackConsoleErrors } from './helpers';

test('le bouton de connexion s’active au remplissage, sans navigation', async ({
  page,
}) => {
  const errors = trackConsoleErrors(page);

  await page.goto('/sign-in');

  const submit = page.getByRole('button', { name: 'Se connecter' });

  // Champs vides ( valeurs initiales de useState ) ⇒ bouton désactivé.
  await expect(submit).toBeDisabled();

  // Remplissage : disabled = busy || !email.trim() || !password ⇢ s'active.
  // { exact: true } : le toggle « Afficher le mot de passe » a un
  // aria-label contenant « mot de passe » — sans exact, getByLabel
  // lèverait un strict mode violation ( 2 éléments ).
  await page.getByLabel('Adresse email').fill('alice@example.com');
  await page.getByLabel('Mot de passe', { exact: true }).fill('secret');
  await expect(submit).toBeEnabled();

  // La saisie ne doit PAS déclencher de navigation ( pas de submit ).
  expect(new URL(page.url()).pathname).toBe('/sign-in');

  expect(errors).toEqual([]);
});

test('le toggle du mot de passe bascule la visibilité et son aria-label', async ({
  page,
}) => {
  await page.goto('/sign-in');

  const toggle = page.getByRole('button', {
    name: 'Afficher le mot de passe',
  });

  await expect(toggle).toBeVisible();

  // Clic ⇒ l'aria-label bascule ( et aria-pressed suit ) — c'est ce que
  // les lecteurs d'écran annoncent, on teste l'accessibilité du widget.
  await toggle.click();

  // Après le clic, l'élément porte un AUTRE aria-label : on re-requête
  // avec le nouveau nom ( le locator « Afficher... » ne matche plus ).
  const toggleHidden = page.getByRole('button', {
    name: 'Masquer le mot de passe',
  });
  await expect(toggleHidden).toBeVisible();
  await expect(toggleHidden).toHaveAttribute('aria-pressed', 'true');
});