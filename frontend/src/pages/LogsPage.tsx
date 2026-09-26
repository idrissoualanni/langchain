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
  INFO: 'text-live',
  WARNING: 'text-warning',
  ERROR: 'text-destructive',
};

const EVENT_TONES: Record<string, string> = {
  TOOL_START: 'text-live',
  TOOL_END: 'text-success',
  TOOL_ERROR: 'text-destructive',
  MEMORY_READ: 'text-live',
  MEMORY_WRITE: 'text-success',
  MEMORY_UPDATE: 'text-success',
  MEMORY_DELETE: 'text-warning',
  MEMORY_SEARCH: 'text-live',
  MEMORY_DEDUP: 'text-warning',
  MEMORY_SKIP: 'text-muted-foreground',
  MEMORY_READ_ERROR: 'text-destructive',
  MEMORY_WRITE_ERROR: 'text-destructive',
  MEMORY_UPDATE_ERROR: 'text-destructive',
  MEMORY_DELETE_ERROR: 'text-destructive',
  MEMORY_SEARCH_ERROR: 'text-destructive',
  MEMORY_STORE_INIT: 'text-warning',
  CONTEXT_BUILD_START: 'text-live',
  CONTEXT_BUILD_END: 'text-success',
  CONTEXT_BUILD_ERROR: 'text-destructive',
  ROUTING_START: 'text-live',
  ROUTING_END: 'text-success',
  SUBJECT_CONTEXT_SELECTED: 'text-live',
  KNOWLEDGE_SEARCH: 'text-live',
  KNOWLEDGE_SELECTED: 'text-success',
  TOOLS_SELECTED: 'text-live',
  SUBJECT_REGISTRY_LOADED: 'text-warning',
  SUBJECT_REGISTRY_ERROR: 'text-destructive',
  PROMPT_BUILD: 'text-success',
  USER_MEMORY_SELECTED: 'text-live',
  THREAD_CONTEXT_SELECTED: 'text-live',
  CHECKPOINT_SAVED: 'text-success',
  RUN_START: 'text-live',
  RUN_END: 'text-success',
  ASSISTANT_MESSAGE: 'text-success',
  USER_MESSAGE: 'text-live',
  ERROR: 'text-destructive',
};

function LogLine({ entry }: { entry: LogEntry }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.12 }}
      className="flex items-baseline gap-3 whitespace-nowrap px-4 py-[3px] font-mono text-[11.5px] leading-[1.5] hover:bg-muted/60"
    >
      <span className="shrink-0 text-muted-foreground">
        {entry.timestamp?.split('T')[1]?.slice(0, 8) ?? '--:--:--'}
      </span>
      <span
        className={cn(
          'w-[52px] shrink-0 font-semibold',
          LEVEL_TONES[entry.level] ?? 'text-muted-foreground'
        )}
      >
        {entry.level}
      </span>
      <span
        className={cn(
          'w-[170px] shrink-0 truncate',
          EVENT_TONES[entry.event] ?? 'text-muted-foreground'
        )}
        title={entry.event}
      >
        {entry.event}
      </span>
      {entry.tool_name && (
        <span className="shrink-0 text-warning">[{entry.tool_name}]</span>
      )}
      {entry.thread_id && (
        <span
          className="hidden shrink-0 text-muted-foreground md:inline"
          title={entry.thread_id}
        >
          {entry.thread_id.slice(0, 8)}
        </span>
      )}
      <span className="min-w-0 truncate text-foreground/85" title={entry.message}>
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
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-card/50 px-6 py-3">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-foreground">
            <Terminal size={16} className="text-live" strokeWidth={1.8} />
            Logs
          </h1>
          <p className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
            {connected ? (
              <>
                <Wifi size={10} className="text-success" />
                sse stream · live
              </>
            ) : (
              <>
                <WifiOff size={10} className="text-destructive" />
                déconnecté
              </>
            )}
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={12}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="rechercher…"
              className="h-8 w-44 rounded-lg border border-border bg-muted pl-7 pr-3 font-mono text-[11px] text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-live/50"
            />
          </div>

          {Object.keys(LEVEL_GROUPS).map((group) => (
            <button
              key={group}
              onClick={() => toggleGroup(group)}
              className={cn(
                'rounded-full border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
                activeGroups.has(group)
                  ? 'border-live/50 bg-live/15 text-live'
                  : 'border-border bg-muted text-muted-foreground hover:text-foreground'
              )}
            >
              {group}
            </button>
          ))}

          <div className="mx-1 h-6 w-px bg-border" />

          <button
            onClick={() => (paused ? resume() : setPaused(true))}
            className={cn(
              'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 font-mono text-[11px] font-medium transition-colors',
              paused
                ? 'border-warning/40 bg-warning/10 text-warning'
                : 'border-border bg-muted text-foreground hover:border-live'
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
                ? 'border-success/40 bg-success/10 text-success'
                : 'border-border bg-muted text-muted-foreground'
            )}
          >
            auto-scroll
          </button>

          <button
            onClick={clearDisplay}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-muted px-3 py-1.5 font-mono text-[11px] font-medium text-muted-foreground transition-colors hover:border-destructive/40 hover:text-destructive"
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
        className="min-h-0 flex-1 overflow-auto bg-background py-2"
      >
        <AnimatePresence initial={false}>
          {filtered.length === 0 ? (
            <div className="py-12 text-center font-mono text-[11px] text-muted-foreground">
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
      <div className="flex items-center justify-between border-t border-border bg-card px-6 py-1.5 font-mono text-[10px] text-muted-foreground">
        <span>
          {filtered.length} / {logs.length} lines
        </span>
        <span className="flex items-center gap-2">
          {paused ? '⏸ paused' : '● live'}
          <span className="text-muted-foreground">logs/agent.log</span>
        </span>
      </div>
    </div>
  );
}
