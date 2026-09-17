// Couche d'adaptation Assistant UI — conversion AgentResponse → ThreadMessageLike
//
// Pattern OFFICIEL external-store : "convertMessage" traduit notre
// format vers ThreadMessageLike. La AgentResponse voyage dans une
// DATA PART (name: "agent-response") — le mécanisme d'extensibilité
// documenté (Message primitive : part kinds, kind "data", grows by
// name). Le texte principal reste un part text classique (markdown
// via le MarkdownText officiel).
//
// §18 respecté : la nature de la réponse vient du contrat structuré
// (response.type), JAMAIS du parsing du texte.
import type {
  ThreadMessageLike,
  ThreadUserMessagePart,
  ThreadAssistantMessagePart,
} from '@assistant-ui/react';
import type { StoreMessage } from './types';

/** Nom de la data part portant l'AgentResponse (contrat interne à la couche). */
export const AGENT_RESPONSE_PART = 'agent-response';

/** Data part officielle assistant-ui portant une AgentResponse. */
export interface AgentResponseDataPart {
  type: 'data';
  name: typeof AGENT_RESPONSE_PART;
  data: StoreMessage['agentResponse'];
}

export function toUserMessage(message: StoreMessage): ThreadMessageLike {
  const parts: ThreadUserMessagePart[] = [
    { type: 'text', text: message.content },
  ];
  return {
    id: message.id,
    role: 'user',
    createdAt: new Date(message.createdAt),
    content: parts,
  };
}

export function toAssistantMessage(
  message: StoreMessage,
): ThreadMessageLike {
  const parts: ThreadAssistantMessagePart[] = [];

  // 1. Texte principal — part text standard (markdown officiel)
  if (message.content) {
    parts.push({ type: 'text', text: message.content });
  }

  // 2. AgentResponse — data part officielle → cartes pédagogiques
  if (message.agentResponse) {
    parts.push({
      type: 'data',
      name: AGENT_RESPONSE_PART,
      data: message.agentResponse,
    });
  }

  // 3. Tool calls temps réel — parts tool-call officielles
  for (const call of message.toolCalls ?? []) {
    const argsText =
      typeof call.args === 'string'
        ? call.args
        : JSON.stringify(call.args ?? {});
    parts.push({
      type: 'tool-call',
      toolCallId: call.toolCallId,
      toolName: call.toolName,
      args: (call.args ?? {}) as Record<string, never>,
      argsText,
      ...(call.result !== undefined
        ? { result: call.result as string }
        : {}),
    });
  }

  return {
    id: message.id,
    role: 'assistant',
    createdAt: new Date(message.createdAt),
    content: parts,
  };
}

/** convertMessage officiel (callback useExternalStoreRuntime). */
export function convertMessage(message: StoreMessage): ThreadMessageLike {
  return message.role === 'user'
    ? toUserMessage(message)
    : toAssistantMessage(message);
}

/** Extrait l'AgentResponse d'un ThreadMessageLike reconverti (round-trip). */
export function extractAgentResponse(
  message: ThreadMessageLike,
): StoreMessage['agentResponse'] {
  const parts = message.content as unknown as Array<
    Record<string, unknown>
  >;
  for (const part of parts) {
    if (
      part.type === 'data' &&
      part.name === AGENT_RESPONSE_PART
    ) {
      return part.data as StoreMessage['agentResponse'];
    }
  }
  return undefined;
}
