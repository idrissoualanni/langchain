// QuizCard V6.7 — question de quiz, UNE à la fois (§21).
// Le texte de la question est rendu par le part text officiel ;
// cette carte n'affiche que la progression structurée.
import { motion } from 'framer-motion';
import { ListChecks } from 'lucide-react';
import type { QuizData } from '../../types/agentResponse';

export function QuizCard({ data }: { data: QuizData }) {
  const idx = (data.question_index ?? 0) + 1;
  const total = data.total_questions ?? 0;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-[var(--radius-surface)] border border-success/25 bg-success/[0.05] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <ListChecks size={14} className="text-success" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-success uppercase">
          quiz
        </span>
        {total > 0 && (
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">
            question {idx}/{total}
          </span>
        )}
      </div>
      {total > 0 && (
        <div className="h-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-success/70 transition-all"
            style={{ width: `${(idx / total) * 100}%` }}
          />
        </div>
      )}
    </motion.div>
  );
}
