// Hook Chat — messages, stream SSE, tool executions temps réel
import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  AgentEvent,
  ChatMessage,
  ToolExecution,
} from '../types/agent';
import { streamChatMessage } from '../api/agent';
import { getThreadState } from '../api/memory';
import { connectAgentEvents } from '../api/events';

let idCounter = 0;
const nextId = () => `${Date.now()}-${idCounter++}`;

export type RunStatus = 'idle' | 'running' | 'error';

export function useChat(
  userId: string | null,
  threadId: string | null
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toolExecutions, setToolExecutions] = useState<
    Record<string, ToolExecution>
  >({});
  const [status, setStatus] = useState<RunStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [activity, setActivity] = useState<AgentEvent[]>([]);

  // Track des tools en cours pour ce thread (id → execution)
  const pendingTools = useRef<Map<string, ToolExecution>>(new Map());
  const activeThread = useRef<string | null>(null);
  activeThread.current = threadId;

  // ----- Chargement de l'historique depuis le checkpointer -----
  const loadHistory = useCallback(async () => {
    if (!threadId) {
      setMessages([]);
      return;
    }
    try {
      const state = await getThreadState(
        threadId,
        userId ?? undefined
      );
      const rebuilt: ChatMessage[] = state.messages
        .filter(
          (m) =>
            m.type === 'HumanMessage' ||
            m.type === 'AIMessage'
        )
        .map((m) => ({
          id: nextId(),
          role: m.type === 'HumanMessage' ? 'user' : 'assistant',
          content: m.content,
          timestamp: '',
        }));
      setMessages(rebuilt);
    } catch (e) {
      // Thread sans state LangGraph (vide) — silencieux
      setMessages([]);
    }
  }, [threadId, userId]);

  useEffect(() => {
    loadHistory();
    setToolExecutions({});
    setActivity([]);
    pendingTools.current.clear();
  }, [loadHistory]);

  // ----- Bus SSE global : événements TOOL_* temps réel -----
  useEffect(() => {
    const disconnect = connectAgentEvents((event) => {
      // Filtre : événements du thread courant uniquement
      const evtThread = event.thread_id || '';
      if (activeThread.current && evtThread && evtThread !== activeThread.current) {
        return;
      }

      // Activity feed (pipeline visuel)
      if (
        [
          'RUN_START',
          'STATE_LOAD',
          'TOOL_START',
          'TOOL_END',
          'TOOL_ERROR',
          'ASSISTANT_MESSAGE',
          'CHECKPOINT_SAVED',
          'RUN_END',
          'ERROR',
        ].includes(event.event)
      ) {
        setActivity((prev) => [...prev.slice(-40), event]);
      }

      // Tool executions : RUNNING → SUCCESS / ERROR
      if (event.event === 'TOOL_START' && event.tool_name) {
        const exec: ToolExecution = {
          id: `${event.tool_name}-${event.timestamp}-${Math.random()}`,
          toolName: event.tool_name,
          status: 'running',
          input: event.input ?? event.message,
          timestamp: event.timestamp,
        };
        pendingTools.current.set(exec.id, exec);
        setToolExecutions((prev) => ({ ...prev, [exec.id]: exec }));
      } else if (
        (event.event === 'TOOL_END' || event.event === 'TOOL_ERROR') &&
        event.tool_name
      ) {
        // Associer au tool running le plus récent du même nom
        const running = [...pendingTools.current.values()]
          .filter(
            (t) =>
              t.toolName === event.tool_name && t.status === 'running'
          )
          .pop();
        if (running) {
          const updated: ToolExecution = {
            ...running,
            status:
              event.event === 'TOOL_END' ? 'success' : 'error',
            output: event.output,
            error: event.error,
            durationMs: event.duration_ms,
          };
          pendingTools.current.set(running.id, updated);
          setToolExecutions((prev) => ({
            ...prev,
            [running.id]: updated,
          }));
        }
      }
    });
    return disconnect;
  }, []);

  // ----- Envoi de message -----
  const sendMessage = useCallback(
    async (text: string) => {
      if (!userId || !threadId || !text.trim() || status === 'running') {
        return;
      }

      setStatus('running');
      setError(null);

      // Message utilisateur immédiat
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'user',
          content: text.trim(),
          timestamp: new Date().toISOString(),
        },
      ]);

      try {
        let gotResponse = false;
        await streamChatMessage(userId, threadId, text, (event) => {
          if (
            event.event === 'ASSISTANT_MESSAGE' &&
            event.response
          ) {
            gotResponse = true;
            setMessages((prev) => [
              ...prev,
              {
                id: nextId(),
                role: 'assistant',
                content: event.response!,
                timestamp: event.timestamp,
              },
            ]);
          }
          if (event.event === 'ERROR') {
            setError(event.message ?? 'Erreur agent');
          }
        });

        // Sécurité : si le stream n'a pas donné de réponse (ex: interruption)
        if (!gotResponse) {
          await loadHistory();
        }
      } catch (e) {
        setError(
          e instanceof Error ? e.message : 'Erreur de communication'
        );
      } finally {
        setStatus('idle');
      }
    },
    [userId, threadId, status, loadHistory]
  );

  return {
    messages,
    toolExecutions: Object.values(toolExecutions),
    status,
    error,
    activity,
    sendMessage,
    reload: loadHistory,
  };
}
