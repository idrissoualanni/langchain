// EvaluationCard V6.7 — feedback d'évaluation (§23).
// Jamais de keyword list / hidden answer / scoring interne :
// le backend ne les envoie pas (normalizer §23).
import { motion } from 'framer-motion';
import { CheckCircle2, RotateCcw } from 'lucide-react';
import type { EvaluationData } from '../../types/agentResponse';

const STATUS_STYLE: Record<string, string> = {
  completed: 'border-success/25 bg-success/[0.05]',
  waiting_for_user: 'border-warning/25 bg-warning/[0.05]',
  cancelled: 'border-border bg-muted/40',
  running: 'border-live/25 bg-live/[0.05]',
  error: 'border-destructive/25 bg-destructive/[0.05]',
};

export function EvaluationCard({
  data,
  status,
}: {
  data: EvaluationData;
  status: string;
}) {
  const retry = data.next_action === 'retry_answer';
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-[var(--radius-surface)] border p-3.5 ${
        STATUS_STYLE[status] ?? STATUS_STYLE.completed
      }`}
    >
      <div className="flex items-center gap-2">
        <CheckCircle2 size={14} className="text-success" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
          évaluation
          {typeof data.score === 'number'
            ? ` · ${Math.round(data.score * 100)}%`
            : ''}
        </span>
        {retry && (
          <span className="ml-auto flex items-center gap-1 font-mono text-[10px] text-warning">
            <RotateCcw size={11} /> à retravailler
          </span>
        )}
      </div>
    </motion.div>
  );
}
