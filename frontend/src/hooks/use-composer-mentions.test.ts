import { describe, expect, it } from 'vitest';
import { unstable_defaultDirectiveFormatter } from '@assistant-ui/core';
import {
  activeComposerTerm,
  hasComposerTerm,
  parseComposerTerms,
  removeComposerTerm,
} from './use-composer-mentions';

// Texte RÉELLEMENT inséré par le popover @ quand on choisit un élément :
// le formateur par défaut d'assistant-ui produit une directive, pas "@id".
const inserted = unstable_defaultDirectiveFormatter.serialize({
  id: 'deep-research',
  type: 'mention',
  label: 'Deep Research',
});

describe('mentions @ du composer', () => {
  it('le popover insère bien une directive (prérequis du test)', () => {
    expect(inserted).toBe(':mention[Deep Research]{name=deep-research}');
  });

  it('terme tapé à la main : routage research', () => {
    const r = parseComposerTerms('@deep-research les trous noirs');
    expect(r.workflow).toBe('research');
    expect(r.payload).toEqual({ research_mode: 'deep-research' });
    expect(r.query).toBe('les trous noirs');
  });

  // Reproduction du bug : choisir un terme dans le popover perdait le
  // routage et envoyait la directive brute au modèle.
  it('terme choisi dans le popover : routage research et texte nettoyé', () => {
    const r = parseComposerTerms(`${inserted} les trous noirs`);
    expect(r.workflow).toBe('research');
    expect(r.payload).toEqual({ research_mode: 'deep-research' });
    expect(r.query).toBe('les trous noirs');
  });

  it('directive sans attribut name (id = label)', () => {
    const r = parseComposerTerms(':mention[code] écris un tri');
    expect(r.workflow).toBe('coding');
    expect(r.query).toBe('écris un tri');
  });

  it('une directive inconnue reste dans le texte, sans routage', () => {
    const r = parseComposerTerms(':mention[Inconnu]{name=nope} bonjour');
    expect(r.workflow).toBe('');
    expect(r.query).toContain(':mention[Inconnu]{name=nope}');
  });

  it('le badge détecte et retire le terme quelle que soit la forme', () => {
    expect(hasComposerTerm(`${inserted} x`)).toBe(true);
    expect(activeComposerTerm(`${inserted} x`)?.id).toBe('deep-research');
    expect(removeComposerTerm(`${inserted} x`, 'deep-research')).toBe('x');
    expect(removeComposerTerm('@deep-research x', 'deep-research')).toBe('x');
    expect(hasComposerTerm('bonjour @inconnu')).toBe(false);
  });
});
