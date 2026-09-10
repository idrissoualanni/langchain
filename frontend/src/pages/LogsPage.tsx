// LogsPage — console temps réel
// Terminal : une seule voix, mono, pour de la donnée machine.
// Colonnes alignées : temps · niveau · événement · contexte.
import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Eraser,
  Pause,
  Play,
  Search,
  Terminal,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { useLogs, LEVEL_GROUPS } from '../hooks/useLogs';
import type { LogEntry } from '../types/agent';
import { cn } from '../lib/utils';

const LEVEL_TONES: Record<string, string> = {
  INFO: 'text-[#6c63ff]',
  WARNING: 'text-[#f59e0b]',
  ERROR: 'text-[#ef4444]',
};

const EVENT_TONES: Record<string, string> = {
  TOOL_START: 'text-[#6c63ff]',
  TOOL_END: 'text-[#22c55e]',
  TOOL_ERROR: 'text-[#ef4444]',
  MEMORY_READ: 'text-[#6c63ff]',
  MEMORY_WRITE: 'text-[#22c55e]',
  MEMORY_UPDATE: 'text-[#22c55e]',
  MEMORY_DELETE: 'text-[#f59e0b]',
  MEMORY_SEARCH: 'text-[#6c63ff]',
  MEMORY_DEDUP: 'text-[#f59e0b]',
  MEMORY_SKIP: 'text-[#94a3b8]',
  MEMORY_READ_ERROR: 'text-[#ef4444]',
  MEMORY_WRITE_ERROR: 'text-[#ef4444]',
  MEMORY_UPDATE_ERROR: 'text-[#ef4444]',
  MEMORY_DELETE_ERROR: 'text-[#ef4444]',
  MEMORY_SEARCH_ERROR: 'text-[#ef4444]',
  MEMORY_STORE_INIT: 'text-[#f59e0b]',
  CONTEXT_BUILD_START: 'text-[#6c63ff]',
  CONTEXT_BUILD_END: 'text-[#22c55e]',
  CONTEXT_BUILD_ERROR: 'text-[#ef4444]',
  ROUTING_START: 'text-[#6c63ff]',
  ROUTING_END: 'text-[#22c55e]',
  SUBJECT_CONTEXT_SELECTED: 'text-[#6c63ff]',
  KNOWLEDGE_SEARCH: 'text-[#6c63ff]',
  KNOWLEDGE_SELECTED: 'text-[#22c55e]',
  TOOLS_SELECTED: 'text-[#6c63ff]',
  SUBJECT_REGISTRY_LOADED: 'text-[#f59e0b]',
  SUBJECT_REGISTRY_ERROR: 'text-[#ef4444]',
  PROMPT_BUILD: 'text-[#22c55e]',
  USER_MEMORY_SELECTED: 'text-[#6c63ff]',
  THREAD_CONTEXT_SELECTED: 'text-[#6c63ff]',
  CHECKPOINT_SAVED: 'text-[#22c55e]',
  RUN_START: 'text-[#6c63ff]',
  RUN_END: 'text-[#22c55e]',
  ASSISTANT_MESSAGE: 'text-[#22c55e]',
  USER_MESSAGE: 'text-[#6c63ff]',
  ERROR: 'text-[#ef4444]',
};

function LogLine({ entry }: { entry: LogEntry }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.12 }}
      className="flex items-baseline gap-3 whitespace-nowrap px-4 py-[3px] font-mono text-[11.5px] leading-[1.5] hover:bg-[#18212b]/60"
    >
      <span className="shrink-0 text-[#94a3b8]/50">
        {entry.timestamp?.split('T')[1]?.slice(0, 8) ?? '--:--:--'}
      </span>
      <span
        className={cn(
          'w-[52px] shrink-0 font-semibold',
          LEVEL_TONES[entry.level] ?? 'text-[#94a3b8]'
        )}
      >
        {entry.level}
      </span>
      <span
        className={cn(
          'w-[170px] shrink-0 truncate',
          EVENT_TONES[entry.event] ?? 'text-[#94a3b8]'
        )}
        title={entry.event}
      >
        {entry.event}
      </span>
      {entry.tool_name && (
        <span className="shrink-0 text-[#f59e0b]">[{entry.tool_name}]</span>
      )}
      {entry.thread_id && (
        <span
          className="hidden shrink-0 text-[#94a3b8]/40 md:inline"
          title={entry.thread_id}
        >
          {entry.thread_id.slice(0, 8)}
        </span>
      )}
      <span className="min-w-0 truncate text-[#f5f7fa]/85" title={entry.message}>
        {entry.message}
      </span>
    </motion.div>
  );
}

export function LogsPage() {
  const {
    logs,
    paused,
    connected,
    setPaused,
    resume,
    clearDisplay,
    applyFilters,
  } = useLogs();

  const [search, setSearch] = useState('');
  const [activeGroups, setActiveGroups] = useState<Set<string>>(new Set());
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () =>
      applyFilters(logs, {
        levels: activeGroups,
        events: new Set(),
        search,
        threadId: null,
      }),
    [logs, activeGroups, search, applyFilters]
  );

  useEffect(() => {
    if (autoScroll && !paused) {
      containerRef.current?.scrollTo({
        top: containerRef.current.scrollHeight,
      });
    }
  }, [filtered.length, autoScroll, paused]);

  const toggleGroup = (group: string) => {
    setActiveGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col">
      {/* Barre d'outils */}
      <div className="flex flex-wrap items-center gap-3 border-b border-[#26323d] bg-[#111820]/50 px-6 py-3">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[#f5f7fa]">
            <Terminal size={16} className="text-[#6c63ff]" strokeWidth={1.8} />
            Logs
          </h1>
          <p className="flex items-center gap-1.5 font-mono text-[10px] text-[#94a3b8]">
            {connected ? (
              <>
                <Wifi size={10} className="text-[#22c55e]" />
                sse stream · live
              </>
            ) : (
              <>
                <WifiOff size={10} className="text-[#ef4444]" />
                déconnecté
              </>
            )}
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={12}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#94a3b8]"
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="rechercher…"
              className="h-8 w-44 rounded-lg border border-[#26323d] bg-[#18212b] pl-7 pr-3 font-mono text-[11px] text-[#f5f7fa] placeholder:text-[#94a3b8]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c63ff]/50"
            />
          </div>

          {Object.keys(LEVEL_GROUPS).map((group) => (
            <button
              key={group}
              onClick={() => toggleGroup(group)}
              className={cn(
                'rounded-full border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
                activeGroups.has(group)
                  ? 'border-[#6c63ff]/50 bg-[#6c63ff]/15 text-[#6c63ff]'
                  : 'border-[#26323d] bg-[#18212b] text-[#94a3b8] hover:text-[#f5f7fa]'
              )}
            >
              {group}
            </button>
          ))}

          <div className="mx-1 h-6 w-px bg-[#26323d]" />

          <button
            onClick={() => (paused ? resume() : setPaused(true))}
            className={cn(
              'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 font-mono text-[11px] font-medium transition-colors',
              paused
                ? 'border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#f59e0b]'
                : 'border-[#26323d] bg-[#18212b] text-[#f5f7fa] hover:border-[#364553]'
            )}
          >
            {paused ? <Play size={11} /> : <Pause size={11} />}
            {paused ? 'reprendre' : 'pause'}
          </button>

          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={cn(
              'rounded-lg border px-3 py-1.5 font-mono text-[11px] font-medium transition-colors',
              autoScroll
                ? 'border-[#22c55e]/40 bg-[#22c55e]/10 text-[#22c55e]'
                : 'border-[#26323d] bg-[#18212b] text-[#94a3b8]'
            )}
          >
            auto-scroll
          </button>

          <button
            onClick={clearDisplay}
            className="flex items-center gap-1.5 rounded-lg border border-[#26323d] bg-[#18212b] px-3 py-1.5 font-mono text-[11px] font-medium text-[#94a3b8] transition-colors hover:border-[#ef4444]/40 hover:text-[#ef4444]"
            title="Efface l'affichage — le fichier serveur est conservé"
          >
            <Eraser size={11} />
            clear
          </button>
        </div>
      </div>

      {/* Console */}
      <div
        ref={containerRef}
        className="min-h-0 flex-1 overflow-auto bg-[#0b0f14] py-2"
      >
        <AnimatePresence initial={false}>
          {filtered.length === 0 ? (
            <div className="py-12 text-center font-mono text-[11px] text-[#94a3b8]/50">
              {paused
                ? '⏸ en pause — les événements arrivent en arrière-plan'
                : "en attente d'événements…"}
            </div>
          ) : (
            filtered.map((entry, i) => (
              <LogLine
                key={`${entry.timestamp}-${entry.event}-${i}`}
                entry={entry}
              />
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Pied */}
      <div className="flex items-center justify-between border-t border-[#26323d] bg-[#111820] px-6 py-1.5 font-mono text-[10px] text-[#94a3b8]/70">
        <span>
          {filtered.length} / {logs.length} lines
        </span>
        <span className="flex items-center gap-2">
          {paused ? '⏸ paused' : '● live'}
          <span className="text-[#94a3b8]/40">logs/agent.log</span>
        </span>
      </div>
    </div>
  );
}
