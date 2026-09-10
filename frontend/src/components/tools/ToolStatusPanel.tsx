// ToolStatusPanel — statut live des tools + trace d'exécution du run
//
// Signature visuelle : l'Agent Activity est une TRACE D'EXÉCUTION.
// Colonne vertébrale verticale : chaque étape du run est un nœud,
// les exécutions de tools s'indentent SOUS l'étape qui les a déclenchées
// (encodage de la vraie boucle LLM → tool → LLM de LangGraph).
// Tout ce qui vient de la machine est composé en mono.
import { motion, AnimatePresence } from 'framer-motion';
import {
  CircleDashed,
  Cog,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import type { AgentEvent, ToolExecution, ToolStatus } from '../../types/agent';
import { TOOL_NAMES } from '../../types/agent';

interface ToolStatusPanelProps {
  toolExecutions: ToolExecution[];
  activity: AgentEvent[];
  running: boolean;
}

function toolCurrentStatus(
  name: string,
  executions: ToolExecution[]
): ToolStatus {
  const execs = executions.filter((e) => e.toolName === name);
  const last = execs[execs.length - 1];
  return last?.status ?? 'idle';
}

/* Events visibles dans la trace, avec leur niveau de profondeur.
   TOOL_* et MEMORY_* s'indente sous le run — c'est la hiérarchie réelle. */
const TRACE_EVENTS: Record<string, { label: string; depth: 0 | 1 }> = {
  RUN_START: { label: 'run start', depth: 0 },
  STATE_LOAD: { label: 'state loaded', depth: 0 },
  USER_MESSAGE: { label: 'user message', depth: 0 },
  ROUTING_START: { label: 'routing', depth: 0 },
  ROUTING_END: { label: 'routed', depth: 0 },
  CONTEXT_BUILD_START: { label: 'context build', depth: 0 },
  SUBJECT_CONTEXT_SELECTED: { label: 'subject selected', depth: 1 },
  KNOWLEDGE_SEARCH: { label: 'knowledge search', depth: 1 },
  KNOWLEDGE_SELECTED: { label: 'knowledge selected', depth: 1 },
  TOOLS_SELECTED: { label: 'tools selected', depth: 1 },
  USER_MEMORY_SELECTED: { label: 'memories selected', depth: 1 },
  THREAD_CONTEXT_SELECTED: { label: 'thread context', depth: 1 },
  CONTEXT_BUILD_END: { label: 'context built', depth: 0 },
  PROMPT_BUILD: { label: 'prompt built', depth: 0 },
  TOOL_START: { label: 'tool start', depth: 1 },
  TOOL_END: { label: 'tool end', depth: 1 },
  TOOL_ERROR: { label: 'tool error', depth: 1 },
  MEMORY_READ: { label: 'memory read', depth: 1 },
  MEMORY_WRITE: { label: 'memory write', depth: 1 },
  MEMORY_UPDATE: { label: 'memory update', depth: 1 },
  MEMORY_DELETE: { label: 'memory delete', depth: 1 },
  MEMORY_SEARCH: { label: 'memory search', depth: 1 },
  MEMORY_DEDUP: { label: 'memory dedup', depth: 1 },
  MEMORY_SKIP: { label: 'memory skip', depth: 1 },
  MEMORY_READ_ERROR: { label: 'memory read error', depth: 1 },
  MEMORY_WRITE_ERROR: { label: 'memory write error', depth: 1 },
  ASSISTANT_MESSAGE: { label: 'assistant response', depth: 0 },
  CHECKPOINT_SAVED: { label: 'checkpoint saved', depth: 0 },
  RUN_END: { label: 'run end', depth: 0 },
  ERROR: { label: 'error', depth: 0 },
};

function traceTone(event: AgentEvent): string {
  if (
    event.event === 'TOOL_ERROR' ||
    event.event === 'ERROR' ||
    event.event === 'MEMORY_READ_ERROR' ||
    event.event === 'MEMORY_WRITE_ERROR'
  )
    return 'text-[#ef4444]';
  if (
    event.event === 'TOOL_START' ||
    event.event === 'MEMORY_READ' ||
    event.event === 'CONTEXT_BUILD_START' ||
    event.event === 'USER_MEMORY_SELECTED' ||
    event.event === 'THREAD_CONTEXT_SELECTED' ||
    event.event === 'MEMORY_SEARCH' ||
    event.event === 'ROUTING_START' ||
    event.event === 'KNOWLEDGE_SEARCH' ||
    event.event === 'SUBJECT_CONTEXT_SELECTED' ||
    event.event === 'TOOLS_SELECTED'
  )
    return 'text-[#6c63ff]';
  if (
    event.event === 'TOOL_END' ||
    event.event === 'MEMORY_WRITE' ||
    event.event === 'MEMORY_UPDATE' ||
    event.event === 'MEMORY_DEDUP' ||
    event.event === 'MEMORY_DELETE' ||
    event.event === 'MEMORY_SKIP' ||
    event.event === 'CONTEXT_BUILD_END' ||
    event.event === 'PROMPT_BUILD' ||
    event.event === 'CHECKPOINT_SAVED' ||
    event.event === 'RUN_END' ||
    event.event === 'ROUTING_END' ||
    event.event === 'KNOWLEDGE_SELECTED'
  )
    return 'text-[#22c55e]';
  return 'text-[#94a3b8]';
}

export function ToolStatusPanel({
  toolExecutions,
  activity,
  running,
}: ToolStatusPanelProps) {
  const trace = activity.filter((e) => e.event in TRACE_EVENTS);

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Tools — registre des instruments disponibles */}
      <div className="rounded-xl border border-[#26323d] bg-[#111820] p-4">
        <div className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]">
          tools
        </div>
        <div className="space-y-2">
          {TOOL_NAMES.map((name) => {
            const status = toolCurrentStatus(name, toolExecutions);
            return (
              <div
                key={name}
                className="flex items-center justify-between rounded-lg border border-[#26323d] bg-[#18212b] px-3 py-2"
              >
                <span className="flex items-center gap-2 font-mono text-xs text-[#f5f7fa]">
                  {status === 'running' ? (
                    <Cog size={13} className="animate-spin text-[#6c63ff]" />
                  ) : status === 'success' ? (
                    <CheckCircle2 size={13} className="text-[#22c55e]" />
                  ) : status === 'error' ? (
                    <XCircle size={13} className="text-[#ef4444]" />
                  ) : (
                    <CircleDashed size={13} className="text-[#94a3b8]/50" />
                  )}
                  {name}
                </span>
                <span
                  className={`font-mono text-[10px] font-semibold uppercase tracking-wide ${
                    status === 'running'
                      ? 'text-[#6c63ff]'
                      : status === 'success'
                        ? 'text-[#22c55e]'
                        : status === 'error'
                          ? 'text-[#ef4444]'
                          : 'text-[#94a3b8]/60'
                  }`}
                >
                  {status}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Trace d'exécution — la signature */}
      <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-[#26323d] bg-[#111820] p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]">
            execution trace
          </span>
          {running && (
            <span className="flex items-center gap-1.5 font-mono text-[10px] text-[#6c63ff]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#6c63ff] pulse-dot" />
              running
              <span className="caret-blink">▍</span>
            </span>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          <AnimatePresence initial={false}>
            {trace.length === 0 && (
              <div className="py-6 font-mono text-[11px] text-[#94a3b8]/50">
                <p>En attente d'un run…</p>
                <p className="mt-2 text-[#94a3b8]/40">
                  Chaque message déclenchera une trace complète :
                  <br />
                  state → llm → tool → llm → checkpoint
                </p>
              </div>
            )}
            <div className="space-y-0">
              {trace.map((event, i) => {
                const meta = TRACE_EVENTS[event.event];
                const isLast = i === trace.length - 1;
                return (
                  <motion.div
                    key={`${event.timestamp}-${event.event}-${i}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.18 }}
                    className="relative flex gap-2.5 py-1"
                    style={{ paddingLeft: meta.depth === 1 ? 18 : 0 }}
                  >
                    {/* Colonne vertébrale */}
                    {!isLast && (
                      <div className="absolute left-[4px] top-4 h-full w-px bg-[#26323d]" />
                    )}
                    {/* Nœud : losange checkpoint, carré mémoire, point sinon */}
                    <div className="relative mt-[5px] shrink-0">
                      {event.event === 'CHECKPOINT_SAVED' ? (
                        <div className="h-[9px] w-[9px] rotate-45 border border-[#22c55e] bg-[#22c55e]/30" />
                      ) : event.event === 'TOOL_START' ||
                        event.event === 'TOOL_END' ||
                        event.event === 'TOOL_ERROR' ||
                        event.event === 'MEMORY_READ' ||
                        event.event === 'MEMORY_WRITE' ||
                        event.event === 'MEMORY_READ_ERROR' ||
                        event.event === 'MEMORY_WRITE_ERROR' ? (
                        <div
                          className={`h-[9px] w-[9px] rounded-sm ${
                            event.event === 'TOOL_ERROR' ||
                            event.event === 'MEMORY_READ_ERROR' ||
                            event.event === 'MEMORY_WRITE_ERROR'
                              ? 'bg-[#ef4444]'
                              : event.event === 'TOOL_START' ||
                                  event.event === 'MEMORY_READ'
                                ? 'bg-[#6c63ff]'
                                : 'bg-[#22c55e]'
                          }`}
                        />
                      ) : (
                        <div className="h-[9px] w-[9px] rounded-full border border-[#364553] bg-[#18212b]" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <span
                        className={`font-mono text-[11px] ${traceTone(event)}`}
                      >
                        {meta.label}
                        {event.tool_name ? (
                          <span className="text-[#f59e0b]">
                            {' '}
                            {event.tool_name}
                          </span>
                        ) : null}
                      </span>
                      <span className="ml-2 font-mono text-[10px] text-[#94a3b8]/50">
                        {event.timestamp?.split('T')[1]?.slice(0, 8)}
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
