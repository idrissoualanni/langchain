// Typage global pour le bridge de token d'authentification.
//
// NeonTokenBridge pose window.__neonGetToken : apiFetch l'appelle pour
// récupérer le JWT Neon ( Ed25519 ) envoyé en Authorization: Bearer.
export {};

declare global {
  interface Window {
    __neonGetToken?: () => Promise<string | null>;
  }
}
