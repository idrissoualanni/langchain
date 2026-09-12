// EvaluationCard V6.7 — feedback d'évaluation (§23).
// Jamais de keyword list / hidden answer / scoring interne :
// le backend ne les envoie pas (normalizer §23).
import { motion } from 'framer-motion';
import { CheckCircle2, RotateCcw } from 'lucide-react';
import type { EvaluationData } from '../../types/agentResponse';

const STATUS_STYLE: Record<string, string> = {
  completed: 'border-[#22c55e]/25 bg-[#22c55e]/[0.05]',
  waiting_for_user: 'border-[#f59e0b]/25 bg-[#f59e0b]/[0.05]',
  cancelled: 'border-[#94a3b8]/25 bg-[#94a3b8]/[0.05]',
  running: 'border-[#6c63ff]/25 bg-[#6c63ff]/[0.05]',
  error: 'border-[#ef4444]/25 bg-[#ef4444]/[0.05]',
};

export function EvaluationCard({
  message,
  data,
  status,
}: {
  message: string;
  data: EvaluationData;
  status: string;
}) {
  const retry = data.next_action === 'retry_answer';
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl border p-3.5 ${
        STATUS_STYLE[status] ?? STATUS_STYLE.completed
      }`}
    >
      <div className="mb-2 flex items-center gap-2">
        <CheckCircle2 size={14} className="text-[#22c55e]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#94a3b8]">
          évaluation
          {typeof data.score === 'number'
            ? ` · ${Math.round(data.score * 100)}%`
            : ''}
        </span>
        {retry && (
          <span className="ml-auto flex items-center gap-1 font-mono text-[10px] text-[#f59e0b]">
            <RotateCcw size={11} /> à retravailler
          </span>
        )}
      </div>
      <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
    </motion.div>
  );
}
