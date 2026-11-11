/**
 * Feature flags du frontend.
 *
 * Une fonctionnalité dont le backend n'est pas prêt (route absente,
 * service non câblé) est désactivée ici plutôt que livrée cassée.
 * Chaque flag a une valeur par défaut figée dans le code et peut être
 * forcé au build par une variable Vite publique :
 *
 *   VITE_FEATURE_ADMIN_EXERCISES=true   → adminExercises activé
 *
 * Valeurs reconnues : true/1/on/yes et false/0/off/no (casse ignorée).
 * Toute autre valeur est ignorée : le défaut s'applique.
 *
 * Inventaire et raison de chaque flag : docs/FEATURE_FLAGS.md.
 */

export const FEATURE_FLAGS = {
  /** Bibliothèque d'exercices admin — /api/admin/exercises* absent du backend. */
  adminExercises: false,
  /** Liste des groupes (accès savoir) — /api/admin/groups absent du backend. */
  adminGroups: false,
} as const;

export type FeatureFlag = keyof typeof FEATURE_FLAGS;

type Env = Record<string, string | boolean | undefined>;

/** adminExercises → VITE_FEATURE_ADMIN_EXERCISES */
export function flagEnvName(flag: FeatureFlag): string {
  return `VITE_FEATURE_${flag.replace(/[A-Z]/g, (c) => `_${c}`).toUpperCase()}`;
}

function parseBool(value: string | boolean | undefined): boolean | undefined {
  if (typeof value === 'boolean') return value;
  const v = value?.trim().toLowerCase();
  if (v === 'true' || v === '1' || v === 'on' || v === 'yes') return true;
  if (v === 'false' || v === '0' || v === 'off' || v === 'no') return false;
  return undefined;
}

export function isFeatureEnabled(
  flag: FeatureFlag,
  env: Env = import.meta.env as Env,
): boolean {
  return parseBool(env[flagEnvName(flag)]) ?? FEATURE_FLAGS[flag];
}
