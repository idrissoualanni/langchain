"use client";

import { unstable_useMentionAdapter } from "@assistant-ui/react";

/**
 * Mentions du Composer → termes de workflow.
 *
 * AVANT : les @mentions étaient purement décoratives (le popover
 * s'ouvrait mais `onInserted` ne faisait rien — le terme était envoyé
 * tel quel dans le message, le backend ne voyait qu'un texte brut).
 *
 * MAINTENANT : au send, `parseComposerTerms` extrait les termes de la
 * saisie, les retire du texte envoyé au modèle (le "@" ne pollue plus
 * la requête) et les convertit en :
 *   - `workflow`   : hint consommé par WORKFLOW_ROUTER (validé contre
 *                    KNOWN_WORKFLOWS côté backend — un terme inconnu y
 *                    est ignoré + tracé, jamais d'erreur 400)
 *   - `payload`    : entrée structurée du workflow (§8 SubgraphInput) —
 *                    ex: research_mode pour orienter la synthèse
 *
 * Mapping termes → workflow (cohérent avec WIRED_WORKFLOWS backend) :
 *   deep-research / academic-search / news-search → research
 *   video                                          → video
 *   code                                           → coding
 *   agenda                                         → document (MCP calendar §40)
 *   exercise                                       → activity
 */

export interface ComposerTerm {
  /** Identifiant du terme (sans le @). */
  id: string;
  /** Workflow backend ciblé (KNOWN_WORKFLOWS). */
  workflow: string;
  /** Mode affiné porté par le payload (research uniquement). */
  mode?: string;
  label: string;
  description: string;
  icon: string;
}

export const COMPOSER_TERMS: readonly ComposerTerm[] = [
  {
    id: "deep-research",
    workflow: "research",
    mode: "deep-research",
    label: "Deep Research",
    description: "Recherche approfondie multi-sources avec analyse critique",
    icon: "🔬",
  },
  {
    id: "academic-search",
    workflow: "research",
    mode: "academic-search",
    label: "Recherche Académique",
    description: "Priorité aux articles scientifiques et publications",
    icon: "🎓",
  },
  {
    id: "news-search",
    workflow: "research",
    mode: "news-search",
    label: "Actualités Récentes",
    description: "Sources d'actualité des dernières 48h",
    icon: "📰",
  },
  {
    id: "video",
    workflow: "video",
    label: "Vidéo",
    description: "Interagir avec une vidéo (transcription, segments)",
    icon: "🎥",
  },
  {
    id: "agenda",
    workflow: "document",
    label: "Agenda",
    description: "Vérifier disponibilités ou créer un événement (MCP calendar)",
    icon: "📅",
  },
  {
    id: "code",
    workflow: "coding",
    label: "Coding Session",
    description: "Démarrer une session de codage assisté avec sandbox",
    icon: "💻",
  },
  {
    id: "exercise",
    workflow: "activity",
    label: "Exercice",
    description: "Suggestion d'une activité d'exercice (ACTIVITY_TYPE_EXERCISE)",
    icon: "🧩",
  },
];

const TERM_IDS = new Set(COMPOSER_TERMS.map((t) => t.id));

/**
 * Adaptation officielle `unstable_useMentionAdapter` (doc : items
 * `{ id, type, label }`). Ici `type` porte le NOM du déclencheur de
 * workflow (deep-research, agenda…) — le popover l'expose via
 * `item.type`, et `parseComposerTerms` fait le reste au send.
 */
export function useComposerMentions() {
  return unstable_useMentionAdapter({
    items: COMPOSER_TERMS.map((t) => ({
      id: t.id,
      type: "mention",
      label: t.label,
      description: t.description,
      icon: t.icon,
    })),
    includeModelContextTools: false,
  });
}

export interface ParsedComposerTerms {
  /** Workflow ciblé ("" si aucun terme — chaîne principale). */
  workflow: string;
  /** Texte nettoyé des termes (envoyé au modèle). */
  query: string;
  /** Entrée structurée du workflow (research_mode…). Vide si non pertinent. */
  payload: Record<string, string>;
}

/**
 * Extrait les termes `@xxx` d'un texte au moment du send.
 *
 * Règles :
 *   - un terme est reconnu ssi il existe dans COMPOSER_TERMS (un
 *     `@nimportequoi` reste dans le texte — le modèle le voit, le
 *     backend l'ignore côté routage : pas de routage accidentel) ;
 *   - le PREMIER terme gagne sur le workflow (les suivants de même
 *     famille sont retirés du texte aussi, pour garder la requête
 *     propre) ;
 *   - les termes sont retirés du query et l'espace résiduel normalisé
 *     (un message qui ne contient QUE des termes renvoie un query
 *     vide → le store garde le texte original pour l'affichage et
 *     laisse le backend valider le message vide).
 */
export function parseComposerTerms(text: string): ParsedComposerTerms {
  const raw = text ?? "";
  const found: ComposerTerm[] = [];
  let cleaned = raw.replace(
    /@([a-z][a-z0-9-]*)/gi,
    (_match, id: string) => {
      const term = COMPOSER_TERMS.find((t) => t.id === id.toLowerCase());
      if (term) {
        if (!found.some((f) => f.id === term.id)) found.push(term);
        return " "; // retiré du query
      }
      return _match; // terme inconnu : conservé dans le texte
    },
  );

  // Normalise les espaces créés par les retraits (sans toucher aux
  // retours ligne — un saut de ligne est sémantique dans un énoncé).
  cleaned = cleaned.replace(/[ \t]+/g, " ").replace(/^[ \t]+|[ \t]+$/g, "");

  const primary = found[0];
  const payload: Record<string, string> = {};
  if (primary?.mode) {
    payload.research_mode = primary.mode;
  }

  return {
    workflow: primary?.workflow ?? "",
    query: cleaned,
    payload,
  };
}

/** True si le texte contient au moins un terme reconnu (UI : badge). */
export function hasComposerTerm(text: string): boolean {
  const ids = text?.match(/@([a-z][a-z0-9-]*)/gi) ?? [];
  return ids.some((token) => TERM_IDS.has(token.slice(1).toLowerCase()));
}
