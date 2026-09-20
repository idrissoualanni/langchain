// Couche d'adaptation Assistant UI — Tool UIs (renderers de tool-call)
//
// Assistant UI rend chaque tool-call via part.toolUI (enregistré par
// useAssistantToolUI) ou le ToolFallback par défaut. Chaque renderer
// produit une carte pliante ToolCall dédiée à un outil backend.
//
// Les noms enregistrés sont STRICTEMENT les TOOL_NAMES backend réels
// (types/agent.ts — ex: recherche_web, execute_code, create_quiz…) ;
// l'ancien enregistrement `search_documents` ne correspondait à aucun
// outil backend et tombait donc systématiquement sur le fallback.
'use client';

import { useState } from 'react';
import {
  useAssistantToolUI,
  type ToolCallMessagePartComponent,
} from '@assistant-ui/react';
import { ToolCall } from '@/components/assistant-ui/elements/tool-call';
import { TOOL_NAMES } from '@/types/agent';

/** Libellés affichés dans la carte pliante, par outil backend. */
const TOOL_META: Record<string, { label: string; activeLabel: string }> = {
  recherche_web: {
    label: 'Recherche web',
    activeLabel: 'Recherche web en cours',
  },
  get_user_profile: {
    label: 'Profil chargé',
    activeLabel: 'Lecture du profil',
  },
  update_user_profile: {
    label: 'Profil mis à jour',
    activeLabel: 'Mise à jour du profil',
  },
  get_user_memory: {
    label: 'Mémoire chargée',
    activeLabel: 'Lecture de la mémoire',
  },
  save_user_memory: {
    label: 'Mémoire enregistrée',
    activeLabel: 'Enregistrement en mémoire',
  },
  update_user_memory: {
    label: 'Mémoire mise à jour',
    activeLabel: 'Mise à jour de la mémoire',
  },
  delete_user_memory: {
    label: 'Mémoire effacée',
    activeLabel: 'Effacement en mémoire',
  },
  search_user_memory: {
    label: 'Mémoire parcourue',
    activeLabel: 'Recherche en mémoire',
  },
  create_exercise: {
    label: 'Exercice créé',
    activeLabel: 'Création de l’exercice',
  },
  evaluate_answer: {
    label: 'Réponse évaluée',
    activeLabel: 'Évaluation de la réponse',
  },
  give_hint: {
    label: 'Indice fourni',
    activeLabel: 'Génération de l’indice',
  },
  get_learning_profile: {
    label: 'Profil d’apprentissage chargé',
    activeLabel: 'Lecture du profil d’apprentissage',
  },
  get_learning_topic: {
    label: 'Sujet chargé',
    activeLabel: 'Lecture du sujet',
  },
  record_learning_observation: {
    label: 'Observation enregistrée',
    activeLabel: 'Enregistrement de l’observation',
  },
  update_learning_goal: {
    label: 'Objectif mis à jour',
    activeLabel: 'Mise à jour de l’objectif',
  },
  create_quiz: {
    label: 'Quiz créé',
    activeLabel: 'Création du quiz',
  },
  create_quiz_next: {
    label: 'Question suivante',
    activeLabel: 'Préparation de la question suivante',
  },
  assess_understanding: {
    label: 'Compréhension évaluée',
    activeLabel: 'Évaluation de la compréhension',
  },
  propose_review: {
    label: 'Révision proposée',
    activeLabel: 'Préparation de la révision',
  },
  execute_code: {
    label: 'Code exécuté',
    activeLabel: 'Exécution du code',
  },
  run_tests: {
    label: 'Tests exécutés',
    activeLabel: 'Exécution des tests',
  },
  analyze_code: {
    label: 'Code analysé',
    activeLabel: 'Analyse du code',
  },
};

/** Premier argument chaîne de l'appel — affiché comme "query" dans la
 *  carte (ex: la requête de recherche, le code, la question…). */
function firstStringArg(args?: Record<string, unknown>): string {
  if (!args) return '';
  for (const value of Object.values(args)) {
    if (typeof value === 'string' && value.trim()) {
      const trimmed = value.trim();
      return trimmed.length > 60
        ? `${trimmed.slice(0, 60)}…`
        : trimmed;
    }
  }
  return '';
}

/** Résultat rendu en texte (la carte ToolCall n'affiche que du texte). */
function formatResult(result: unknown): string {
  if (result === null || result === undefined) return '';
  if (typeof result === 'string') return result;
  try {
    return JSON.stringify(result);
  } catch {
    return String(result);
  }
}

/** Carte pliante générique pour un outil backend. Utilisée pour tous
 *  les TOOL_NAMES : un mappage dédié par libellés suffit, chaque
 *  outil ayant sa propre entrée dans le registre Assistant UI. */
function makeToolUI(toolName: string): ToolCallMessagePartComponent<
  Record<string, unknown>,
  unknown
> {
  const meta = TOOL_META[toolName];
  const label = meta?.label ?? toolName;
  const activeLabel = meta?.activeLabel ?? `${toolName} en cours`;
  const ToolUI: ToolCallMessagePartComponent<
    Record<string, unknown>,
    unknown
  > = ({ args, argsText, result, status }) => {
    const [open, setOpen] = useState(false);
    return (
      <ToolCall
        label={label}
        activeLabel={activeLabel}
        query={firstStringArg(args)}
        request={argsText}
        result={formatResult(result)}
        running={status.type === 'running'}
        open={open}
        onOpenChange={setOpen}
      />
    );
  };
  ToolUI.displayName = `ToolUI(${toolName})`;
  return ToolUI;
}

/** Registre des renderers — construit UNE fois à l'import (identité de
 *  composant stable par outil, sinon Assistant UI les remonterait à
 *  chaque rendu). */
const TOOL_UIS: Record<string, ToolCallMessagePartComponent<
  Record<string, unknown>,
  unknown
>> = Object.fromEntries(
  TOOL_NAMES.map((toolName) => [toolName, makeToolUI(toolName)]),
);

/** Enregistre les Tool UIs tant qu'il est monté.
 *  À appeler DANS l'arbre AssistantRuntimeProvider (cf. AssistantPage).
 *  Tous les outils backend réels (TOOL_NAMES) sont couverts — aucun ne
 *  tombe plus sur le ToolFallback générique. */
export function useToolUIs() {
  for (const toolName of TOOL_NAMES) {
    // TOOL_NAMES est un tuple constant : l'ordre des hooks est stable.
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useAssistantToolUI({
      toolName,
      render: TOOL_UIS[toolName],
    });
  }
}
