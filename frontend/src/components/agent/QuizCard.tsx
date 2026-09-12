// QuizCard V6.7 — question de quiz, UNE à la fois (§21).
import { motion } from 'framer-motion';
import { ListChecks } from 'lucide-react';
import type { QuizData } from '../../types/agentResponse';

export function QuizCard({
  message,
  data,
}: {
  message: string;
  data: QuizData;
}) {
  const idx = (data.question_index ?? 0) + 1;
  const total = data.total_questions ?? 0;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#22c55e]/25 bg-[#22c55e]/[0.05] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <ListChecks size={14} className="text-[#22c55e]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#22c55e]">
          quiz
        </span>
        {total > 0 && (
          <span className="ml-auto font-mono text-[10px] text-[#94a3b8]">
            question {idx}/{total}
          </span>
        )}
      </div>
      {total > 0 && (
        <div className="mb-2.5 h-1 overflow-hidden rounded-full bg-[#0b0f14]">
          <div
            className="h-full rounded-full bg-[#22c55e]/70 transition-all"
            style={{ width: `${(idx / total) * 100}%` }}
          />
        </div>
      )}
      <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
    </motion.div>
  );
}
