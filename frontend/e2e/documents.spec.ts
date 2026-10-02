// Scénarios E2E — page Documents ( RAG utilisateur ) sur API mockée.
//
// POURQUOI ces tests : la page est protégée ( session Neon ) et parle
// au backend via /api/users/{id}/documents. En mockant la session
// Better Auth ( get-session + /token ) et l'API documents avec un
// magasin ÉTATIQUE, on teste le parcours réel de l'utilisateur :
// liste, indexation des documents de test ( e2e/fixtures/documents ),
// suppression AVEC confirmation, refus d'un fichier trop volumineux.
//
// Le confirm() natif est auto-REJETÉ par Playwright : chaque test qui
// touche la suppression enregistre explicitement son comportement de
// dialogue ( accepter / rejeter ) — le rejet doit laisser la donnée
// intacte, c'est précisément ce qu'on vérifie.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page, type Route } from '@playwright/test';

import { loadFrontendEnv, makeFakeJwt, trackConsoleErrors } from './helpers';

const FIXTURES = fileURLToPath(
  new URL('./fixtures/documents', import.meta.url)
);

const USER = {
  user_id: 'e2e-user-1',
  name: 'Élève E2E',
  created_at: '2026-01-01T00:00:00Z',
  external_user_id: 'neon-1',
  role: 'user',
};

const NEON_USER = {
  id: 'neon-1',
  name: 'Élève E2E',
  email: 'eleve@example.com',
  emailVerified: true,
};

interface Doc {
  doc_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
}

function makeDoc(filename: string, sizeBytes = 1024): Doc {
  return {
    doc_id: `doc-${filename}`,
    filename,
    content_type: 'text/plain',
    size_bytes: sizeBytes,
    chunk_count: 3,
    created_at: '2026-10-01T10:00:00',
  };
}

/** Mocks réseau ( session Neon + API documents étatique ).
 *
 *  Le magasin `store` vit le temps du test : POST ajoute, DELETE
 *  retire — chaque GET reflète l'état courant, exactement comme le
 *  backend ferait. */
async function mockAuthenticatedBackend(page: Page, initialDocs: Doc[]) {
  const env = loadFrontendEnv();
  const neon = env.VITE_NEON_AUTH_URL;
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000';

  // Session Better Auth + JWT ( seul `exp` est lu côté navigateur ).
  await page.route(`${neon}/get-session`, (route) =>
    route.fulfill({
      json: {
        user: NEON_USER,
        session: { id: 'sess-e2e', expiresAt: '2030-01-01T00:00:00Z' },
      },
    })
  );
  await page.route(`${neon}/token`, (route) =>
    route.fulfill({ json: { token: makeFakeJwt(3600) } })
  );

  // Échange JWT ↔ cookie HttpOnly ( POST ) + purge ( DELETE ).
  await page.route(`${apiUrl}/api/auth/session`, (route) =>
    route.fulfill({ status: 200, body: '{}' })
  );

  // Utilisateur interne confirmé par le backend ( GET /api/users/me ).
  await page.route(`${apiUrl}/api/users/me`, (route) =>
    route.fulfill({ json: USER })
  );

  // API documents — un seul handler pour la collection et les items.
  const store = [...initialDocs];
  await page.route(
    `${apiUrl}/api/users/${USER.user_id}/documents**`,
    async (route: Route) => {
      const req = route.request();
      const method = req.method();
      if (method === 'GET') return route.fulfill({ json: store });
      if (method === 'POST') {
        const body = req.postDataJSON() as {
          filename?: string;
          content?: string;
        };
        const doc = makeDoc(body.filename ?? 'sans-nom.txt', body.content?.length ?? 0);
        store.push(doc);
        return route.fulfill({ json: doc });
      }
      if (method === 'DELETE') {
        const id = req.url().split('/').pop() ?? '';
        const i = store.findIndex((d) => d.doc_id === id);
        if (i >= 0) store.splice(i, 1);
        return route.fulfill({ json: { deleted: i >= 0, doc_id: id } });
      }
      return route.fulfill({ status: 405, body: '{}' });
    }
  );

  // Silences utiles : threads de la sidebar + health.
  await page.route('**/api/threads**', (route) =>
    route.fulfill({ json: [] })
  );
  await page.route('**/api/health**', (route) =>
    route.fulfill({ json: { status: 'ok' } })
  );
}

// ------------------------------------------------------------------
// Garde de session
// ------------------------------------------------------------------

test.describe('Documents — garde de session', () => {
  test('/documents sans session renvoie vers /sign-in', async ({ page }) => {
    const env = loadFrontendEnv();
    const errors = trackConsoleErrors(page);

    // Aucune session Neon : Better Auth répond null.
    await page.route(`${env.VITE_NEON_AUTH_URL}/get-session`, (route) =>
      route.fulfill({ json: null })
    );

    await page.goto('/documents');
    await expect(page).toHaveURL(/\/sign-in$/);
    expect(errors).toEqual([]);
  });
});

// ------------------------------------------------------------------
// Parcours documents ( API mockée )
// ------------------------------------------------------------------

test.describe('Documents — bibliothèque ( API mockée )', () => {
  test('liste, indexation du document de test, puis suppression confirmée', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const errors = trackConsoleErrors(page);
    await mockAuthenticatedBackend(page, [makeDoc('notes-revisions.txt')]);

    await page.goto('/documents');
    await expect(page.getByText('Documents', { exact: true }).first()).toBeVisible();

    // La bibliothèque mockée est là…
    await expect(page.getByText('notes-revisions.txt')).toBeVisible();

    // … puis on indexe le document de test .md ( input caché du formulaire ).
    await page
      .locator('input[type="file"]:not([aria-label])')
      .setInputFiles(path.join(FIXTURES, 'cours-photosynthese.md'));
    // Le nom est pré-rempli par la sélection du fichier.
    await expect(page.getByPlaceholder('nom-du-fichier.md')).toHaveValue(
      'cours-photosynthese.md'
    );
    await page.getByRole('button', { name: 'Indexer' }).click();
    await expect(page.getByText('cours-photosynthese.md')).toBeVisible();

    // Suppression : menu d'actions → confirm natif ACCEPTÉ.
    await page
      .getByRole('button', { name: 'Actions sur cours-photosynthese.md' })
      .click();
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('menuitem', { name: 'Supprimer' }).click();

    // Le GET suivant ( refresh après delete ) ne contient plus le doc.
    await expect(page.getByText('cours-photosynthese.md')).toHaveCount(0);
    await expect(page.getByText('notes-revisions.txt')).toBeVisible();

    expect(errors).toEqual([]);
  });

  test('suppression ANNULEE : le document est conservé', async ({ page }) => {
    test.setTimeout(120_000);
    await mockAuthenticatedBackend(page, [makeDoc('notes-revisions.txt')]);

    await page.goto('/documents');
    await expect(page.getByText('notes-revisions.txt')).toBeVisible();

    await page
      .getByRole('button', { name: 'Actions sur notes-revisions.txt' })
      .click();
    // Playwright rejette le confirm() par défaut → le DELETE ne part pas.
    await page.getByRole('menuitem', { name: 'Supprimer' }).click();

    // Toujours là après un battement de cils.
    await page.waitForTimeout(500);
    await expect(page.getByText('notes-revisions.txt')).toBeVisible();
  });

  test('fichier > 2 Mo refusé avec un message explicite', async ({ page }) => {
    test.setTimeout(120_000);
    await mockAuthenticatedBackend(page, []);

    await page.goto('/documents');
    await expect(page.getByRole('button', { name: 'Indexer' })).toBeVisible();

    // 3 Mo de zéros : MAX_BYTES = 2 Mo dans la page.
    await page
      .locator('input[type="file"]:not([aria-label])')
      .setInputFiles({
        name: 'gros-fichier.txt',
        mimeType: 'text/plain',
        buffer: Buffer.alloc(3_000_000),
      });

    await expect(page.getByRole('alert')).toContainText(
      'Fichier trop volumineux — 2 Mo maximum.'
    );
    // Rien n'a été prérempli : l'indexation reste impossible.
    await expect(page.getByRole('button', { name: 'Indexer' })).toBeDisabled();
  });

  test('indexation du PDF de test ( lecture base64 )', async ({ page }) => {
    test.setTimeout(120_000);
    await mockAuthenticatedBackend(page, []);

    await page.goto('/documents');

    await page
      .locator('input[type="file"]:not([aria-label])')
      .setInputFiles(path.join(FIXTURES, 'extrait-cours.pdf'));
    await expect(page.getByPlaceholder('nom-du-fichier.md')).toHaveValue(
      'extrait-cours.pdf'
    );
    await page.getByRole('button', { name: 'Indexer' }).click();

    await expect(page.getByText('extrait-cours.pdf')).toBeVisible();
  });
});
