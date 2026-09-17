// Couche d'adaptation Assistant UI — types
// Mission : Assistant UI = couche interface/transport. Le backend
// (AgentResponse, Learning Engine, RAG, mémoire, fallback) reste
// la source de vérité — ces types ne dupliquent PAS les contrats
// internes backend (BuiltContext, RoutingResult, SearchResponse,
// FallbackDecision, LearningProfile restent backend-only).
import type {
  AgentResponse,
} from '../types/agentResponse';

export type { AgentResponse };

/** Message de notre store — format interne à la couche d'adaptation. */
export interface StoreMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
  /** AgentResponse structurée (messages assistant V6.7+). */
  agentResponse?: AgentResponse;
  /** Tool calls temps réel (bus /api/events) pour ce message. */
  toolCalls?: LiveToolCall[];
}

/** Tool call en cours/terminé — alimenté par le bus SSE /api/events. */
export interface LiveToolCall {
  toolCallId: string;
  toolName: string;
  args?: unknown;
  result?: unknown;
  state: 'running' | 'complete' | 'error';
}

/** Thread backend (contrat ThreadOut — inchangé). */
export interface BackendThread {
  thread_id: string;
  user_id: string;
  name: string;
  created_at: string;
}

/** Modèle exposé par GET /api/models (contrat ModelInfo). */
export interface BackendModel {
  id: string;
  name: string;
  description: string;
  active: boolean;
}

export interface BackendModelsResponse {
  models: BackendModel[];
  active_model: string;
}

/** Événement du bus global /api/events (sous-ensemble utile ici). */
export interface AgentBusEvent {
  event: string;
  thread_id?: string;
  tool_name?: string;
  message?: string;
  input?: string;
  output?: string;
  error?: string;
  agent_response?: AgentResponse;
  timestamp?: string;
}

let idCounter = 0;
export const nextId = (prefix: string): string =>
  `${prefix}-${Date.now().toString(36)}-${idCounter++}`;
