// ToolExecutionCard — exécution réelle d'un tool, animée
// RUNNING (pulse + spinner) → SUCCESS (check spring) / ERROR (rouge)
// Input/output en mono : c'est de la donnée machine.
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, Check, Wrench } from 'lucide-react';
import type { ToolExecution } from '../../types/agent';

export function ToolExecutionCard({
  execution,
}: {
  execution: ToolExecution;
}) {
  const isRunning = execution.status === 'running';
  const isError = execution.status === 'error';
  const isSuccess = execution.status === 'success';

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className={`max-w-md rounded-lg border bg-[#18212b]/70 ${
        isRunning
          ? 'border-[#6c63ff]/50 tool-pulse'
          : isError
            ? 'border-[#ef4444]/40'
            : 'border-[#26323d]'
      }`}
    >
      {/* En-tête : nom du tool + statut */}
      <div className="flex items-center gap-2.5 px-3.5 py-2.5">
        <div
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
            isRunning
              ? 'bg-[#6c63ff]/15 text-[#6c63ff]'
              : isError
                ? 'bg-[#ef4444]/15 text-[#ef4444]'
                : 'bg-[#22c55e]/15 text-[#22c55e]'
          }`}
        >
          {isRunning ? (
            <Wrench size={13} className="animate-spin" />
          ) : isError ? (
            <AlertCircle size={13} />
          ) : (
            <AnimatePresence mode="wait">
              <motion.span
                key="check"
                initial={{ scale: 0, rotate: -90 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: 'spring', stiffness: 350, damping: 18 }}
              >
                <Check size={13} strokeWidth={3} />
              </motion.span>
            </AnimatePresence>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <span className="font-mono text-[13px] font-semibold text-[#f5f7fa]">
            {execution.toolName}
            <span className="ml-1.5 text-[#94a3b8]/60">()</span>
          </span>
        </div>

        {execution.durationMs !== undefined && (
          <span className="shrink-0 font-mono text-[10px] text-[#94a3b8]">
            {execution.durationMs}ms
          </span>
        )}
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider ${
            isRunning
              ? 'bg-[#6c63ff]/15 text-[#6c63ff]'
              : isError
                ? 'bg-[#ef4444]/15 text-[#ef4444]'
                : isSuccess
                  ? 'bg-[#22c55e]/15 text-[#22c55e]'
                  : 'bg-[#26323d] text-[#94a3b8]'
          }`}
        >
          {isRunning ? 'running' : isError ? 'error' : isSuccess ? 'success' : 'idle'}
        </span>
      </div>

      {/* Input */}
      {execution.input && (
        <div className="border-t border-[#26323d]/60 px-3.5 py-2">
          <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-[#94a3b8]/70">
            args
          </div>
          <div className="rounded bg-[#0b0f14] px-2.5 py-1.5 font-mono text-[11px] text-[#94a3b8]">
            {execution.input}
          </div>
        </div>
      )}

      {/* Output / Error */}
      <AnimatePresence>
        {isSuccess && execution.output !== undefined && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="overflow-hidden border-t border-[#26323d]/60 px-3.5 py-2"
          >
            <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-[#22c55e]/80">
              returns
            </div>
            <div className="rounded bg-[#0b0f14] px-2.5 py-1.5 font-mono text-[11px] text-[#f5f7fa]">
              {execution.output || '(void)'}
            </div>
          </motion.div>
        )}
        {isError && execution.error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="overflow-hidden border-t border-[#ef4444]/20 px-3.5 py-2"
          >
            <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-[#ef4444]/80">
              raises
            </div>
            <div className="rounded bg-[#0b0f14] px-2.5 py-1.5 font-mono text-[11px] text-[#ef4444]">
              {execution.error}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
