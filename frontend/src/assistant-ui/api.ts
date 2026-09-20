// Couche d'adaptation Assistant UI — client transport
//
// Transport choisi (design validé) : les endpoints FastAPI
// EXISTANTS du backend pédagogique — aucun protocole imposé par
// Assistant UI (pas d'AssistantChatTransport : le backend ne parle
// pas le protocole UI message stream, et la mission interdit de le
// migrer). C'est la couche d'adaptation qui traduit.
//
// Endpoints consommés (tous préexistants, sauf les deux ajouts
// documentés de la mission) :
//   POST /api/chat                      — run complet (fallback)
//   GET  /api/chat/stream               — run streamé SSE (pipeline)
//   GET/POST /api/users/{id}/threads    — threads (préexistant)
//   PUT  /api/threads/{id}              — renommage (ajout mission)
//   GET  /api/threads/{id}/state        — historique checkpointer
//   GET  /api/models                    — ModelSelector (ajout mission)
//   GET  /api/events                    — bus SSE tool-calls temps réel
import type {
  AgentBusEvent,
  BackendModelsResponse,
  BackendThread,
  StoreMessage,
} from './types';
// Mission Identité (§19) : TOUT le transport passe par la couche
// centrale ( api/base.ts ) → Bearer token injecté UNE fois ,
// partout ( jsonFetch , threads , SSE ).
import {
  ApiError,
  apiFetch as jsonFetch,
  apiFetchRaw,
} from '../api/base';

// ------------------------------------------------------------------
// Threads (contrat existant + renommage)
// ------------------------------------------------------------------

export async function listThreads(
  userId: string,
): Promise<BackendThread[]> {
  return jsonFetch<BackendThread[]>(`/api/users/${userId}/threads`);
}

export async function createThread(
  userId: string,
  name: string,
): Promise<BackendThread> {
  return jsonFetch<BackendThread>(`/api/users/${userId}/threads`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export async function renameThread(
  threadId: string,
  name: string,
): Promise<BackendThread> {
  return jsonFetch<BackendThread>(`/api/threads/${threadId}`, {
    method: 'PUT',
    body: JSON.stringify({ name }),
  });
}

export async function deleteThread(threadId: string): Promise<void> {
  // apiFetchRaw ne lève jamais sur status HTTP : on vérifie
  // explicitement, sinon un DELETE refusé (401/403/404) serait
  // traité comme un succès et le thread ne serait retiré qu'en
  // local → il réapparaîtrait au rechargement.
  const res = await apiFetchRaw(`/api/threads/${threadId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail =
        typeof body?.detail === 'string'
          ? body.detail
          : JSON.stringify(body?.detail ?? body);
    } catch {
      /* corps vide ou non-JSON */
    }
    throw new ApiError(res.status, detail);
  }
}

// ------------------------------------------------------------------
// Historique — state checkpointer (contrat StateResponse)
// ------------------------------------------------------------------

interface StateResponseMessage {
  type: string;
  content: string;
}

interface StateResponse {
  user_id: string;
  thread_id: string;
  interaction_count: number;
  message_count: number;
  messages: StateResponseMessage[];
}

export async function loadThreadHistory(
  threadId: string,
): Promise<StoreMessage[]> {
  try {
    const state = await jsonFetch<StateResponse>(
      `/api/threads/${threadId}/state`,
    );
    return state.messages
      .filter(
        (m) => m.type === 'HumanMessage' || m.type === 'AIMessage',
      )
      .map((m, i) => ({
        id: `hist-${threadId}-${i}`,
        role: m.type === 'HumanMessage' ? 'user' : 'assistant',
        content: m.content,
        createdAt: Date.now() - (state.messages.length - i) * 1000,
      }));
  } catch {
    // Thread sans state LangGraph → historique vide (silencieux)
    return [];
  }
}

// ------------------------------------------------------------------
// Chat — stream SSE du pipeline + fallback POST
// ------------------------------------------------------------------

export interface StreamHandlers {
  onAssistantChunk?: (text: string) => void;
  onAgentResponse?: (text: string, agentResponse: unknown) => void;
  onToolStart?: (toolName: string, input?: string) => void;
  onToolEnd?: (toolName: string, output?: string) => void;
  onToolError?: (toolName: string, error: string) => void;
  onError?: (message: string) => void;
}

/** Parse un frame SSE "event: X\ndata: {...}". */
function parseSseFrame(frame: string): AgentBusEvent | null {
  const dataLine = frame
    .split(String.fromCharCode(10))
    .find((l) => l.startsWith('data:'));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice(5).trim()) as AgentBusEvent;
  } catch {
    return null;
  }
}

/**
 * Run streamé via GET /api/chat/stream (SSE pipeline backend).
 * AbortSignal → Stop generation (Cancel du Composer officiel).
 */
export async function streamChat(
  userId: string,
  threadId: string,
  message: string,
  model: string | null,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const params = new URLSearchParams({
    user_id: userId,
    thread_id: threadId,
    message,
  });
  if (model) params.set('model', model);

  // Mission Identité (§17) : le token passe en HEADER ( jamais en
  // URL ) — fetch streaming SSE , solution compatible headers.
  const res = await apiFetchRaw(
    `/api/chat/stream?${params.toString()}`,
    { headers: { Accept: 'text/event-stream' }, signal },
  );

  if (!res.ok || !res.body) {
    // Fallback officiel documenté (api/agent.ts existant) : POST
    const fallback = await jsonFetch<{
      response: string;
      agent_response: unknown;
    }>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        thread_id: threadId,
        message,
        ...(model ? { model } : {}),
      }),
    });
    handlers.onAssistantChunk?.(fallback.response);
    handlers.onAgentResponse?.(
      fallback.response,
      fallback.agent_response,
    );
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    if (signal.aborted) {
      reader.cancel().catch(() => undefined);
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split(String.fromCharCode(10, 10));
    buffer = frames.pop() ?? '';

    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (!event) continue;
      switch (event.event) {
        case 'ASSISTANT_MESSAGE':
          handlers.onAgentResponse?.(
            event.message ?? '',
            event.agent_response,
          );
          break;
        case 'TOOL_START':
          handlers.onToolStart?.(
            event.tool_name ?? 'tool',
            event.input ?? event.message,
          );
          break;
        case 'TOOL_END':
          handlers.onToolEnd?.(
            event.tool_name ?? 'tool',
            event.output ?? event.message,
          );
          break;
        case 'TOOL_ERROR':
          handlers.onToolError?.(
            event.tool_name ?? 'tool',
            event.error ?? event.message ?? 'erreur outil',
          );
          break;
        case 'ERROR':
          handlers.onError?.(
            event.message ?? 'Erreur du pipeline agent',
          );
          break;
        default:
          break;
      }
    }
  }
}

// ------------------------------------------------------------------
// Models — ModelSelector officiel (ajout mission)
// ------------------------------------------------------------------

export async function listModels(): Promise<BackendModelsResponse> {
  return jsonFetch<BackendModelsResponse>('/api/models');
}

// ------------------------------------------------------------------
// Bus global — /api/events (tool-calls temps réel, hors stream)
// ADMIN (§22) : EventSource ne supporte pas les headers → token
// en query `auth` ( preuve VÉRIFIÉE backend , cf sse.py ) , 401/403
// refusent la connexion.
// ------------------------------------------------------------------

const EVENTS_BASE = import.meta.env.VITE_API_URL || '';

export function connectAgentBus(
  onEvent: (event: AgentBusEvent) => void,
): () => void {
  const source = new EventSource(`${EVENTS_BASE}/api/events`);
  source.addEventListener('agent-event', (e) => {
    try {
      onEvent(JSON.parse((e as MessageEvent).data));
    } catch {
      /* ignore */
    }
  });
  source.onerror = () => {
    // EventSource re-connecte automatiquement (comportement natif)
  };
  return () => source.close();
}
