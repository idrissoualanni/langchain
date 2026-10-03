// Thème appliqué avant le premier paint (évite le flash blanc).
//
// EXTRAIT DE index.html — et le déplacement est délibéré : il rend la
// directive `script-src 'self'` de la CSP tenable. Un script EN LIGNE
// dans index.html impose `'unsafe-inline'`… lequel autorise à nouveau
// l'exécution de n'importe quel script injecté par une XSS. C'est-à-dire
// que la CSP perdrait précisément la protection qu'on cherche à obtenir.
// Un fichier externe, lui, est couvert par `'self'` sans exception.
//
// Chargé par un <script src> classique (ni `defer`, ni `async`, ni
// `type="module"`) : il s'exécute donc de façon synchrone, à sa place
// dans le flux du <head>, exactement comme le script inline le faisait —
// le thème est posé avant le premier rendu, sans régression de FOUC.
//
// La logique elle-même est inchangée : `localStorage('dsh_theme')`, sinon
// préférence système.
try {
  var pref = localStorage.getItem('dsh_theme');
  var dark =
    pref === 'dark' ||
    (pref !== 'light' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  if (dark) document.documentElement.classList.add('dark');
} catch (e) {}