import { defineConfig, devices } from '@playwright/test';

// Config e2e Playwright.
//   - Tests : e2e/*.spec.ts ( le runner vitest couvre les tests unitaires ).
//   - Serveur web : Playwright démarre lui-même vite ( webServer ) sur le
//     port 5173 ; `reuseExistingServer` évite un doublon si le dev tourne déjà.
//   - Navigateur : Chromium uniquement pour la démo ( aucun test dépendant
//     des autres moteurs pour l'instant ).
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // 1 worker : la démo ne dépend d'aucune donnée partagée.
  // Machine chargée : le premier compile vite + l'événement `load` de la page
  // peuvent dépasser 30 s. Le `load` ET le teardown du contexte comptent dans
  // le timeout de test — on garde une marge large pour éviter les faux échecs
  // purement environnementaux.
  timeout: 90_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    // Timeout d'une navigation borné à 45 s : si le `load` complet traîne
    // ( police, worker vite, animation ), on échoue vite au lieu de brûler
    // les 90 s du test.
    navigationTimeout: 45_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
});