import { describe, expect, it } from 'vitest';
import { FEATURE_FLAGS, flagEnvName, isFeatureEnabled } from './flags';

describe('feature flags', () => {
  it('dérive le nom de variable Vite du nom du flag', () => {
    expect(flagEnvName('adminExercises')).toBe('VITE_FEATURE_ADMIN_EXERCISES');
    expect(flagEnvName('adminGroups')).toBe('VITE_FEATURE_ADMIN_GROUPS');
  });

  it('les fonctionnalités sans backend sont désactivées par défaut', () => {
    expect(FEATURE_FLAGS.adminExercises).toBe(false);
    expect(FEATURE_FLAGS.adminGroups).toBe(false);
    expect(isFeatureEnabled('adminExercises', {})).toBe(false);
  });

  it("l'environnement force le flag dans les deux sens", () => {
    expect(isFeatureEnabled('adminExercises', { VITE_FEATURE_ADMIN_EXERCISES: 'true' })).toBe(true);
    expect(isFeatureEnabled('adminExercises', { VITE_FEATURE_ADMIN_EXERCISES: ' ON ' })).toBe(true);
    expect(isFeatureEnabled('adminExercises', { VITE_FEATURE_ADMIN_EXERCISES: '0' })).toBe(false);
  });

  it('une valeur illisible retombe sur le défaut', () => {
    expect(isFeatureEnabled('adminExercises', { VITE_FEATURE_ADMIN_EXERCISES: 'peut-être' })).toBe(false);
  });
});
