// Couche d'adaptation Assistant UI — store (zustand)
//
// "Your state" du diagramme officiel ExternalStoreRuntime :
// nous possédons messages/threads/isRunning ; le runtime officiel
// rend ce qu'on lui fournit. Un store par user actif + threads.
//
// Règle threads/concepts (officielle) : "Centralize thread id
// state in a context, never in component-local state" → tout
// l'état threads vit ici.
import { create } from 'zustand';
import type {
  AgentResponse,
  BackendThread,
  LiveToolCall,
  StoreMessage,
} from './types';
import { nextId } from './types';
import {
  createThread as apiCreateThread,
  listThreads as apiListThreads,
  loadThreadHistory,
  renameThread as apiRenameThread,
  deleteThread as apiDeleteThread,
  streamChat,
} from './api';
// Panneau d'activité (spec §38) : les événements activity.* du run
// sont dispatchés vers le store d'activité dédié.
import {
  LOCAL_ACTIVITY_PREFIX,
  resolveActivityKind,
  buildActivityTitle,
  useActivityStore,
  type Activity,
  type ActivityStatus,
} from '../hooks/use-activity-store';

interface AssistantStore {
  // ---- Threads (métadonnées — ExternalStoreThreadListAdapter) ----
  threads: BackendThread[];
  threadsLoading: boolean;
  currentThreadId: string | null;

  // ---- Messages du thread courant (linéaire, pattern officiel) ----
  messages: StoreMessage[];
  historyLoading: boolean;

  // ---- Run ----
  isRunning: boolean;
  error: string | null;

  // ---- Modèle sélectionné (ModelSelector) ----
  selectedModel: string | null;

  // ---- Actions internes ----
  loadThreads: (userId: string) => Promise<void>;
  switchThread: (
    userId: string | null,
    threadId: string | null,
  ) => Promise<void>;
  switchToNewThread: (userId: string | null) => Promise<BackendThread | null>;
  rename: (threadId: string, title: string) => Promise<void>;
  removeThread: (threadId: string) => Promise<void>;
  sendMessage: (userId: string, text: string) => Promise<void>;
  cancel: () => void;
  setModel: (model: string | null) => void;
  setError: (error: string | null) => void;
}

/** AbortController du run courant (Stop generation officiel). */
let currentAbort: AbortController | null = null;

/** userId porté par le provider — le store en a besoin pour les
 * actions threads (create/rename) sans le re-passer partout. */
let storeUserId: string | null = null;
export function setStoreUser(userId: string | null) {
  storeUserId = userId;
}

/**
 * Persiste la SÉLECTION du thread courant ( pas une identité ).
 * Le contenu reste la source de vérité du BACKEND ; localStorage
 * ne porte que { thread_id, user_id, name, created_at } pour :
 *   - F5 (§21) : AssistantRuntimeProvider restaure le thread actif ;
 *   - MemoryPage : affiche le contexte actif via useSelection.
 * (Mission Cleanup §6 : jamais d'identité ici.)
 */
function persistSelection(threadId: string) {
  const thread = useAssistantStore
    .getState()
    .threads.find((t) => t.thread_id === threadId);
  const { user_id } = thread ?? { user_id: storeUserId };
  if (!user_id || !threadId) return;
  localStorage.setItem(
    'dsh_current_thread',
    JSON.stringify({
      thread_id: threadId,
      user_id,
      name: thread?.name ?? 'New Chat',
      created_at: thread?.created_at ?? String(Date.now()),
    }),
  );
}

export const useAssistantStore = create<AssistantStore>((set, get) => ({
  threads: [],
  threadsLoading: false,
  currentThreadId: null,
  messages: [],
  historyLoading: false,
  isRunning: false,
  error: null,
  selectedModel: null,

  loadThreads: async (userId) => {
    set({ threadsLoading: true });
    try {
      const threads = await apiListThreads(userId);
      set({ threads, threadsLoading: false });
    } catch (e) {
      set({
        threadsLoading: false,
        error: e instanceof Error ? e.message : 'Erreur threads',
      });
    }
  },

  switchThread: async (userId, threadId) => {
    if (userId === null || threadId === null) {
      set({ currentThreadId: null, messages: [] });
      return;
    }
    set({ currentThreadId: threadId, historyLoading: true, error: null });
    const history = await loadThreadHistory(threadId);
    // Garde-fou : le thread a pu changer pendant le chargement
    if (get().currentThreadId !== threadId) return;
    set({ messages: history, historyLoading: false });
    persistSelection(threadId);
  },

  switchToNewThread: async (userId) => {
    // ThreadListPrimitive.New officiel : crée un thread backend
    // réel (l'UI Basic liste des conversations persistantes).
    if (userId === null) return null;
    try {
      const thread = await apiCreateThread(userId, 'New Chat');
      set((s) => ({
        threads: [thread, ...s.threads],
        currentThreadId: thread.thread_id,
        messages: [],
        historyLoading: false,
        error: null,
      }));
      persistSelection(thread.thread_id);
      return thread;
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Création impossible',
      });
      return null;
    }
  },

  rename: async (threadId, title) => {
    // Renommage inline officiel thread-list.aui → PUT backend
    try {
      const updated = await apiRenameThread(threadId, title);
      set((s) => ({
        threads: s.threads.map((t) =>
          t.thread_id === threadId ? updated : t,
        ),
      }));
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Renommage impossible',
      });
    }
  },

  removeThread: async (threadId) => {
    try {
      await apiDeleteThread(threadId);
      const wasCurrent = get().currentThreadId === threadId;
      set((s) => ({
        threads: s.threads.filter((t) => t.thread_id !== threadId),
        ...(wasCurrent ? { currentThreadId: null, messages: [] } : {}),
      }));
      if (wasCurrent) {
        localStorage.removeItem('dsh_current_thread');
        const remaining = get().threads;
        if (storeUserId && remaining.length > 0) {
          void get().switchThread(storeUserId, remaining[0].thread_id);
        }
      }
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Suppression impossible',
      });
    }
  },

  sendMessage: async (userId, text) => {
    const threadId = get().currentThreadId;
    if (!threadId) {
      set({ error: 'Aucun thread actif — créez une conversation.' });
      return;
    }

    // Message utilisateur optimiste (pattern officiel quickstart)
    const userMsg: StoreMessage = {
      id: nextId('user'),
      role: 'user',
      content: text,
      createdAt: Date.now(),
    };
    // Message assistant vide (streaming "mutate in place" officiel)
    const assistantId = nextId('assistant');
    const assistantMsg: StoreMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      createdAt: Date.now(),
    };
    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      isRunning: true,
      error: null,
    }));

    currentAbort = new AbortController();
    const model = get().selectedModel;

    const patchAssistant = (
      patch: Partial<StoreMessage>,
    ) => {
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId ? { ...m, ...patch } : m,
        ),
      }));
    };

    const liveTools: LiveToolCall[] = [];
    const upsertTool = (call: LiveToolCall) => {
      const idx = liveTools.findIndex(
        (t) => t.toolCallId === call.toolCallId,
      );
      if (idx >= 0) liveTools[idx] = call;
      else liveTools.push(call);
      patchAssistant({ toolCalls: [...liveTools] });
    };

    try {
      await streamChat(
        userId,
        threadId,
        text,
        model,
        {
          onAssistantChunk: (chunk) => {
            const current =
              get().messages.find((m) => m.id === assistantId);
            patchAssistant({
              content: (current?.content ?? '') + chunk,
            });
          },
          onAgentResponse: (fullText, agentResponse) => {
            patchAssistant({
              content: fullText,
              agentResponse: agentResponse as AgentResponse | undefined,
            });
          },
          onToolStart: (toolName, input) => {
            upsertTool({
              toolCallId: nextId('tool'),
              toolName,
              args: input,
              state: 'running',
            });
          },
          onToolEnd: (toolName, output) => {
            // Dernier tool running de ce nom → complete
            const idx = liveTools.findIndex(
              (t) => t.toolName === toolName && t.state === 'running',
            );
            if (idx >= 0) {
              liveTools[idx] = {
                ...liveTools[idx],
                state: 'complete',
                result: output,
              };
              patchAssistant({ toolCalls: [...liveTools] });
            }
          },
          onToolError: (toolName, error) => {
            const idx = liveTools.findIndex(
              (t) => t.toolName === toolName && t.state === 'running',
            );
            if (idx >= 0) {
              liveTools[idx] = {
                ...liveTools[idx],
                state: 'error',
                result: error,
              };
              patchAssistant({ toolCalls: [...liveTools] });
            }
          },
          onError: (message) => {
            set({ error: message });
          },
          onActivity: (event) => {
            // Dispatch vers le store d'activité (panneau §38).
            const id = event.activity_id || nextId('activity');
            const status: ActivityStatus = event.type.endsWith(
              'completed',
            )
              ? 'completed'
              : event.type.endsWith('failed')
                ? 'failed'
                : 'running';
            // Kind §38 : spec §3 activity_type d'abord, sinon le
            // tool_name backend (create_quiz → quiz, execute_code →
            // coding…) — le payload ACTIVITY_STARTED/QUIZ_STARTED n'a
            // pas d'activity_type (pedagogical_tools.py).
            const kind = resolveActivityKind(
              event.activity_type,
              event.tool_name,
            );
            // Titre spec §3 : le backend ne l'envoie pas, on le
            // compose avec subject/topic (présents dans le payload).
            const title = buildActivityTitle({
              title: event.title,
              subject: event.subject,
              topic: event.topic,
              toolName: event.tool_name,
              kind,
            });
            const activityStore = useActivityStore.getState();
            // Réconciliation : l'activité optimiste déposée par le
            // bouton Activité du Composer (encore 'running') est
            // remplacée par l'activité réelle. On privilégie celle
            // qui correspond par kind PUIS title (un Quiz flash local
            // ne doit pas absorber un exercice backend, et inversement)
            // — fallback sur la plus récente encore running.
            const optimisticCandidates =
              activityStore.activities.filter(
                (a) =>
                  a.id.startsWith(LOCAL_ACTIVITY_PREFIX) &&
                  a.status === 'running',
              );
            const optimistic =
              optimisticCandidates.find((a) => a.type === kind) ??
              optimisticCandidates.find((a) => a.title === title) ??
              optimisticCandidates[0];
            if (optimistic) activityStore.removeActivity(optimistic.id);
            const activity: Activity = {
              id,
              type: kind,
              title,
              status,
              data: event.data,
            };
            activityStore.upsertActivity(activity);
            activityStore.setActive(id);
          },
        },
        currentAbort.signal,
      );
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        set({
          error: e instanceof Error ? e.message : 'Erreur de run',
        });
      }
    } finally {
      currentAbort = null;
      set({ isRunning: false });
      // Rafraîchit les métadonnées (ordre des threads backend)
      if (storeUserId) get().loadThreads(storeUserId).catch(() => undefined);
    }
  },

  cancel: () => {
    // Stop generation officiel (ComposerPrimitive.Cancel)
    currentAbort?.abort();
    currentAbort = null;
    set({ isRunning: false });
  },

  setModel: (model) => set({ selectedModel: model }),
  setError: (error) => set({ error }),
}));
