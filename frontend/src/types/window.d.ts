// Volontairement VIDE.
//
// Ce fichier déclarait autrefois `window.__neonGetToken`, le point d'accès
// global utilisé par apiFetch pour poser le header `Authorization: Bearer`.
// Il n'existe plus.
//
// Une fonction sur `window` est lisible par TOUT ce qui s'exécute dans la
// page : une injection de script, une extension, une simple ligne de
// console. Rendre le jeton de session atteignable ainsi revenait à
// announce que toute XSS disposait d'une session complète à exfiltrer.
//
// Le JWT est désormais échangé une fois contre un cookie `HttpOnly` par
// `NeonTokenBridge` ( POST /api/auth/session ), puis n'est plus manipulé
// par le JavaScript : les requêtes le transmettent via
// `credentials: 'include'` et le navigateur fait le reste.
//
// NE PAS réintroduire de secret sur `window`. Si une valeur doit être
// connue du front et du backend, elle se dérive d'un échange serveur —
// pas d'une globale.
export {};