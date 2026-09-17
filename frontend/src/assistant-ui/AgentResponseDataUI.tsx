// Couche d'adaptation Assistant UI — data part "agent-response"
//
// Mécanisme OFFICIEL : useAssistantDataUI({ name, render }) —
// enregistre le renderer de la data part "agent-response" créée
// par convert.ts. Le Thread officiel rendra automatiquement la
// carte pédagogique correspondant à response.type (§18 : la
// nature vient du CONTRAT, jamais du parsing du texte).
//
// Nos cartes existantes (components/agent/*) sont RÉUTILISÉES
// telles quelles — Assistant UI est une couche interface, pas
// un moteur pédagogique (règle absolue de la mission).
'use client';

import { useAssistantDataUI } from '@assistant-ui/react';
import { useAssistantStore } from './store';
import { ResponseRenderer } from '../components/agent/ResponseRenderer';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { AGENT_RESPONSE_PART } from './convert';
import type { AgentResponse } from './types';

/**
 * Data part UI officielle — rend l'AgentResponse via les cartes
 * pédagogiques existantes (ExerciseCard, QuizCard, HintCard,
 * EvaluationCard, CodeActivityCard, SearchResultCard,
 * ClarificationCard, ErrorCard). Le texte est rendu par le part
 * text officiel — les cartes ne rendent que le structuré.
 *
 * Les actions des cartes (request_hint, submit_answer, options
 * de clarification) rejouent la même sémantique que ChatPage
 * existant : envoi d'un message au thread actif.
 */
function AgentResponsePart({
  data,
}: {
  data: AgentResponse;
}) {
  // Mission Identité : user = SESSION ( Clerk/dev )
  const { internal: currentUser, signedIn } = useCurrentUser();
  const sendMessage = useAssistantStore((s) => s.sendMessage);
  const currentThreadId = useAssistantStore((s) => s.currentThreadId);

  return (
    <div className="aui-agent-response-card my-2 max-w-full">
      <ResponseRenderer
        response={data}
        threadId={currentThreadId}
        userId={signedIn ? currentUser?.user_id ?? null : null}
        onAction={(type) => {
          // Actions V6.7 → message chat (même sémantique ChatPage)
          if (type === 'request_hint') {
            void sendMessage(currentUser!.user_id, 'Donne-moi un indice');
          } else if (type === 'submit_answer') {
            // L'étudiant tape SA réponse : focus composer officiel
            document
              .querySelector<HTMLTextAreaElement>(
                'textarea[aria-label="Message input"]',
              )
              ?.focus();
          }
        }}
        onOption={(option) => {
          // Clarification §25 : bouton → réponse directe
          void sendMessage(
            currentUser!.user_id,
            `Je parle de ${option.replace(/_/g, ' ')}.`,
          );
        }}
      />
    </div>
  );
}

/** Enregistre la data part UI (hook officiel) — monter une fois
 *  à l'intérieur du AssistantRuntimeProvider. */
export function useAgentResponseDataUI() {
  useAssistantDataUI({
    name: AGENT_RESPONSE_PART,
    render: ({ data }) => <AgentResponsePart data={data} />,
  });
}
