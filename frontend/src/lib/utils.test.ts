import { describe, expect, it } from 'vitest';
import { cn } from './utils';

describe('cn (fusion de classes Tailwind)', () => {
  it('fusionne et déduplique les conflits', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4');
  });
  it('ignore les valeurs falsy', () => {
    expect(cn('a', false, undefined, null, '')).toBe('a');
  });
  it('supporte les conditions objet', () => {
    expect(cn('base', { hidden: true, flex: false })).toContain('hidden');
  });
});
