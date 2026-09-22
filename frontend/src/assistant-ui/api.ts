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
  ActivityStreamEvent,
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
  /** Événement d'activité pédagogique (spec §3) → store d'activité. */
  onActivity?: (event: ActivityStreamEvent) => void;
  onError?: (message: string) => void;
}

/** Nom + payload d'un frame SSE "event: X\ndata: {...}". */
interface SseFrame {
  /** Nom de l'événement : ligne `event:` sinon champ `event` du JSON. */
  name: string;
  payload: AgentBusEvent;
}

/** Parse un frame SSE. Le nom vient de la ligne `event:` quand elle
 *  existe (le backend émet `event: ACTIVITY_STARTED\ndata: {...}`),
 *  sinon du champ `event` du payload — pour rester compatible avec
 *  les événements qui ne portent le type que dans les données. */
function parseSseFrame(frame: string): SseFrame | null {
  const lines = frame.split(String.fromCharCode(10));
  const dataLine = lines.find((l) => l.startsWith('data:'));
  if (!dataLine) return null;
  let payload: AgentBusEvent;
  try {
    payload = JSON.parse(dataLine.slice(5).trim()) as AgentBusEvent;
  } catch {
    return null;
  }
  const eventLine = lines.find((l) => l.startsWith('event:'));
  const name = eventLine
    ? eventLine.slice(6).trim()
    : (payload.event ?? '');
  return { name, payload };
}

/** Normalise un événement d'activité (spec §3) pour le store.
 *  Propage tool_name/subject/topic : le backend actuel n'envoie NI
 *  activity_type NI title (payload extra de ACTIVITY_STARTED/QUIZ_STARTED
 *  = activity_id/subject/topic/status/source), le store d'activité en
 *  déduit donc kind et titre depuis ces champs (resolveActivityKind /
 *  buildActivityTitle). */
function toActivityEvent(
  type: ActivityStreamEvent['type'],
  payload: AgentBusEvent,
): ActivityStreamEvent {
  return {
    type,
    activity_id: payload.activity_id ?? '',
    activity_type: payload.activity_type,
    title: payload.title,
    status: payload.status,
    data: payload.data,
    tool_name: payload.tool_name,
    subject: payload.subject,
    topic: payload.topic,
  };
}

/**
 * Classe un nom d'événement SSE en phase d'activité (spec §3), ou null
 * si l'événement ne concerne pas le cycle d'activité.
 *
 * Le backend n'émet PAS les noms spec §3 (activity.started/completed/
 * failed). Il émet en réalité (log_event, app/agent/pedagogical_tools.py) :
 *   - ACTIVITY_STARTED (create_exercise), QUIZ_STARTED (create_quiz)
 *     → création d'une activité ;
 *   - QUIZ_COMPLETED (create_quiz) → quiz terminé (a activity_id) ;
 *   - ACTIVITY_STORE_SAVE (app/activity/store.py) → persiste le state
 *     avec son status : "completed"/"abandoned" = terminaison réelle.
 *
 * On mappe donc les noms RÉELS vers les phases spec §3, tout en
 * gardant les noms spec (activity.*) pour l'avenir. Les événements
 * intermédiaires (ACTIVITY_WAITING, QUIZ_QUESTION, ACTIVITY_EVALUATED…)
 * ne sont pas des terminaisons : score<0.4 mène à waiting_for_retry,
 * l'activité continue — on les ignore pour ne pas fermer prématurément
 * une activité en cours.
 */
function classifyActivityEvent(
  name: string,
  payload: AgentBusEvent,
): ActivityStreamEvent['type'] | null {
  switch (name) {
    // ---- Démarrage (spec §3 + noms backend réels) ----
    case 'activity.started':
    case 'ACTIVITY_STARTED':
    case 'QUIZ_STARTED':
      return 'activity.started';
    // ---- Terminaison réussie ----
    case 'activity.completed':
    case 'ACTIVITY_COMPLETED':
    case 'QUIZ_COMPLETED':
      return 'activity.completed';
    // ---- Échec / abandon ----
    case 'activity.failed':
    case 'ACTIVITY_FAILED':
    case 'ACTIVITY_ABANDONED':
      return 'activity.failed';
    // ---- Persistance du state : terminaison selon `status` ----
    case 'ACTIVITY_STORE_SAVE': {
      const st = payload.status ?? '';
      if (st === 'completed') return 'activity.completed';
      if (st === 'abandoned') return 'activity.failed';
      return null; // running/waiting → pas une terminaison
    }
    default:
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
  /** Hint de workflow + payload structuré (§8) issus des termes du
   *  composer (@deep-research → workflow=research…). Optionnels —
   *  absence = routage déterministe habituel. */
  workflow?: string | null,
  payload?: Record<string, string> | null,
): Promise<void> {
  const params = new URLSearchParams({
    user_id: userId,
    thread_id: threadId,
    message,
  });
  if (model) params.set('model', model);
  if (workflow) params.set('workflow', workflow);
  // Le payload est un objet → sérialisé en JSON dans l'URL (le backend
  // le décode ; un JSON invalide y est ignoré + tracé, jamais un 400).
  if (payload && Object.keys(payload).length > 0) {
    params.set('payload', JSON.stringify(payload));
  }

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
        ...(workflow ? { workflow } : {}),
        ...(payload && Object.keys(payload).length > 0
          ? { payload }
          : {}),
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
      const parsed = parseSseFrame(frame);
      if (!parsed) continue;
      const { name, payload: event } = parsed;
      switch (name) {
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
        // ---- Activités pédagogiques (spec §3/§38) ----
        // Le backend émet ses propres noms (ACTIVITY_STARTED,
        // QUIZ_STARTED, QUIZ_COMPLETED, ACTIVITY_STORE_SAVE…) et non
        // les noms spec §3 : classifyActivityEvent fait la traduction.
        // Événements intermédiaires (WAITING, QUIZ_QUESTION,
        // ACTIVITY_EVALUATED…) → ignorés : l'activité continue.
        default: {
          const phase = classifyActivityEvent(name, event);
          if (phase) {
            handlers.onActivity?.(toActivityEvent(phase, event));
          }
          break;
        }
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
