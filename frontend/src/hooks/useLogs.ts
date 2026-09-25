// Hook Logs — console temps réel avec SSE + backfill
import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentEvent, LogEntry } from '../types/agent';
import { getLogs } from '../api/logs';
import { connectAgentEvents } from '../api/events';

export interface LogFilters {
  levels: Set<string>;
  events: Set<string>;
  search: string;
  threadId: string | null;
}

export const LEVEL_GROUPS: Record<string, string[]> = {
  INFO: ['INFO'],
  WARNING: ['WARNING'],
  ERROR: ['ERROR'],
  TOOL: ['TOOL_START', 'TOOL_END', 'TOOL_ERROR', 'TOOL_CALL', 'TOOL_RESULT'],
  THREAD: ['THREAD_CREATE', 'USER_CREATE', 'RUN_START', 'RUN_END'],
  STATE: ['STATE_LOAD', 'CHECKPOINT_SAVED'],
};

export function useLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [connected, setConnected] = useState(false);
  const pausedRef = useRef(false);
  const bufferRef = useRef<LogEntry[]>([]);

  pausedRef.current = paused;

  // Backfill initial depuis l'API
  useEffect(() => {
    getLogs(200)
      .then((entries) => setLogs(entries))
      .catch(() => setLogs([]));
  }, []);

  // Flux SSE temps réel
  useEffect(() => {
    // connected ne passe à true qu'au PREMIER événement reçu — pas à
    // l'abonnement. Sinon l'UI affiche "connecté" avant la première
    // frame SSE ( une connexion qui aurait pu échouer silencieusement ).
    let firstFrame = true;
    const disconnect = connectAgentEvents((event: AgentEvent) => {
      const entry: LogEntry = {
        timestamp: event.timestamp,
        level: event.level,
        event: event.event,
        user_id: event.user_id,
        thread_id: event.thread_id,
        tool_name: event.tool_name,
        message: event.message,
      };
      if (firstFrame) {
        firstFrame = false;
        setConnected(true);
      }
      if (pausedRef.current) {
        bufferRef.current.push(entry);
      } else {
        setLogs((prev) => [...prev.slice(-499), entry]);
      }
    });
    return () => {
      disconnect();
      setConnected(false);
    };
  }, []);

  const resume = useCallback(() => {
    // Reprise : flush du buffer accumulé pendant la pause
    setPaused(false);
    if (bufferRef.current.length > 0) {
      const buffered = [...bufferRef.current];
      bufferRef.current = [];
      setLogs((prev) => [...prev, ...buffered].slice(-500));
    }
  }, []);

  const clearDisplay = useCallback(() => {
    // Clear frontend uniquement — le fichier serveur est conservé
    setLogs([]);
    bufferRef.current = [];
  }, []);

  const applyFilters = useCallback(
    (logs: LogEntry[], filters: LogFilters) => {
      return logs.filter((l) => {
        if (filters.levels.size > 0 && !filters.levels.has(l.level)) {
          // Vérifier aussi les groupes d'événements
          const inGroup = Object.entries(LEVEL_GROUPS).some(
            ([, events]) =>
              filters.levels.has(events[0] === 'INFO' ? 'INFO' : '') &&
              events.includes(l.event)
          );
          const groupMatch = [...filters.levels].some((fl) => {
            const group = LEVEL_GROUPS[fl];
            return group && group.includes(l.event);
          });
          if (!inGroup && !groupMatch) return false;
        }
        if (
          filters.events.size > 0 &&
          !filters.events.has(l.event)
        ) {
          return false;
        }
        if (filters.threadId && l.thread_id !== filters.threadId) {
          return false;
        }
        if (filters.search) {
          const hay = `${l.event} ${l.message ?? ''} ${
            l.tool_name ?? ''
          }`.toLowerCase();
          if (!hay.includes(filters.search.toLowerCase())) return false;
        }
        return true;
      });
    },
    []
  );

  return {
    logs,
    paused,
    connected,
    setPaused,
    resume,
    clearDisplay,
    applyFilters,
  };
}
