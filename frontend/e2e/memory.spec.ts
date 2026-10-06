// Scénarios E2E — page "Mon Cerveau" (Mémoire Utilisateur).
//
// Ces tests vérifient l'accès sécurisé, la gestion de l'identité (persona)
// et la recherche sémantique dans la mémoire cognitive de l'utilisateur.
import { expect, test, type Page, type Route } from '@playwright/test';

import { loadFrontendEnv, makeFakeJwt, trackConsoleErrors } from './helpers';

const USER = {
  user_id: 'e2e-memory-user',
  name: 'Élève Mémoire',
  created_at: '2026-01-01T00:00:00Z',
  external_user_id: 'neon-memory-1',
  role: 'user',
};

const NEON_USER = {
  id: 'neon-memory-1',
  name: 'Élève Mémoire',
  email: 'memoire@example.com',
  emailVerified: true,
};

interface MemoryFact {
  id: string;
  category: string;
  content: string;
  confidence: number;
  updated_at: string;
}

interface UserProfile {
  name: string | null;
  description: string | null;
}

/** Mocks réseau pour la mémoire cognitive. */
async function mockMemoryBackend(page: Page, initialProfile: UserProfile, initialFacts: Record<string, MemoryFact[]>) {
  const env = loadFrontendEnv();
  const neon = env.VITE_NEON_AUTH_URL;
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000';

  // Session Better Auth
  await page.route(`${neon}/get-session`, (route) =>
    route.fulfill({
      json: {
        user: NEON_USER,
        session: { id: 'sess-mem', expiresAt: '2030-01-01T00:00:00Z' },
      },
    })
  );
  await page.route(`${neon}/token`, (route) =>
    route.fulfill({ json: { token: makeFakeJwt(3600) } })
  );

  await page.route(`${apiUrl}/api/auth/session`, (route) =>
    route.fulfill({ status: 200, body: '{}' })
  );

  await page.route(`${apiUrl}/api/users/me`, (route) =>
    route.fulfill({ json: USER })
  );

  // État local pour le profil et les faits
  let currentProfile = { ...initialProfile };
  let currentFacts = { ...initialFacts };

  // Overview: /api/user/memory/overview
  await page.route(`${apiUrl}/api/user/memory/overview`, (route) =>
    route.fulfill({
      json: {
        identity: currentProfile,
        facts_by_category: currentFacts,
      },
    })
  );

  // Update Profile: PATCH /api/user/memory/profile
  await page.route(`${apiUrl}/api/user/memory/profile`, async (route) => {
    const body = route.request().postDataJSON() as UserProfile;
    currentProfile = { ...currentProfile, ...body };
    return route.fulfill({ json: currentProfile });
  });

  // Search: /api/user/memory/cognitive/search
  await page.route(`${apiUrl}/api/user/memory/cognitive/search*`, (route) => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get('query') || '';

    // Simulation simple de recherche sémantique
    const results = [];
    Object.entries(currentFacts).forEach(([category, facts]) => {
      facts.forEach(f => {
        if (f.content.toLowerCase().includes(query.toLowerCase())) {
          results.push({
            content: f.content,
            metadata: { category },
            type: category,
            score: 0.95,
          });
        }
      });
    });

    return route.fulfill({ json: results });
  });

  // Silence
  await page.route('**/api/health**', (route) => route.fulfill({ json: { status: 'ok' } }));
  await page.route('**/api/threads**', (route) => route.fulfill({ json: [] }));
}

test.describe('Mon Cerveau — Accès et Fonctionnalités', () => {

  test('/memory sans session renvoie vers /sign-in', async ({ page }) => {
    const env = loadFrontendEnv();
    const errors = trackConsoleErrors(page);

    await page.route(`${env.VITE_NEON_AUTH_URL}/get-session`, (route) =>
      route.fulfill({ json: null })
    );

    await page.goto('/memory');
    await expect(page).toHaveURL(/\/sign-in$/);
    expect(errors).toEqual([]);
  });

  test('modification du résumé identitaire est mise à jour', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    const initialProfile = { name: 'Ancien Nom', description: 'Ancienne description' };
    const initialFacts = { 'loisirs': [{ id: '1', category: 'loisirs', content: 'Aime le tennis', confidence: 1, updated_at: '2026-01-01' }] };

    await mockMemoryBackend(page, initialProfile, initialFacts);

    await page.goto('/memory');

    // Vérifier état initial
    await expect(page.getByText('Ancien Nom')).toBeVisible();
    await expect(page.getByText('Ancienne description')).toBeVisible();

    // Cliquer sur Modifier
    await page.getByRole('button', { name: 'Modifier' }).click();

    // Saisir nouvelles valeurs
    await page.getByLabel('Nom').fill('Nouveau Nom');
    await page.getByLabel('Description').fill('Nouvelle description mise à jour');

    // Sauvegarder
    await page.getByRole('button', { name: 'Sauvegarder' }).click();

    // Vérifier mise à jour à l'écran
    await expect(page.getByText('Nouveau Nom')).toBeVisible();
    await expect(page.getByText('Nouvelle description mise à jour')).toBeVisible();
    await expect(page.getByText('Ancien Nom')).not.toBeVisible();

    expect(errors).toEqual([]);
  });

  test('recherche sémantique affiche des résultats', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    const profile = { name: 'Test User', description: 'Desc' };
    const facts = {
      'compétences': [
        { id: 'c1', category: 'compétences', content: 'Maîtrise de TypeScript', confidence: 1, updated_at: '2026-01-01' },
        { id: 'c2', category: 'compétences', content: 'Expert en React', confidence: 1, updated_at: '2026-01-01' },
      ],
      'goûts': [
        { id: 'g1', category: 'goûts', content: 'Préfère le café noir', confidence: 1, updated_at: '2026-01-01' },
      ]
    };

    await mockMemoryBackend(page, profile, facts);

    await page.goto('/memory');

    // Recherche pour "TypeScript"
    const searchInput = page.getByPlaceholder('Interroger ma mémoire cognitive...');
    await searchInput.fill('TypeScript');
    await page.getByRole('button', { name: 'Chercher' }).click();

    // Vérifier résultat
    await expect(page.getByText('Maîtrise de TypeScript')).toBeVisible();
    await expect(page.getByText('Expert en React')).not.toBeVisible();

    // Recherche pour "café"
    await searchInput.fill('café');
    await page.getByRole('button', { name: 'Chercher' }).click();
    await expect(page.getByText('Préfère le café noir')).toBeVisible();

    // Recherche sans résultat
    await searchInput.fill('Physique Quantique');
    await page.getByRole('button', { name: 'Chercher' }).click();
    await expect(page.getByText('Aucun souvenir correspondant trouvé')).toBeVisible();

    expect(errors).toEqual([]);
  });
});
