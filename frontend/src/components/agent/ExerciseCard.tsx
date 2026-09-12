// ExerciseCard V6.7 — exercice en attente de réponse (§20).
// Réutilise le style projet ; actions submit/hint pour le chat.
import { motion } from 'framer-motion';
import { Dumbbell, HelpCircle, Send } from 'lucide-react';
import type { ExerciseData } from '../../types/agentResponse';

export function ExerciseCard({
  message,
  data,
  actions,
  onAction,
}: {
  message: string;
  data: ExerciseData;
  actions: { type: string }[];
  onAction?: (type: string) => void;
}) {
  const hasSubmit = actions.some((a) => a.type === 'submit_answer');
  const hasHint = actions.some((a) => a.type === 'request_hint');

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#6c63ff]/25 bg-[#6c63ff]/[0.06] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <Dumbbell size={14} className="text-[#6c63ff]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#6c63ff]">
          exercice
          {data.topic ? ` · ${data.topic}` : ''}
        </span>
      </div>
      <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
      {(hasSubmit || hasHint) && (
        <div className="mt-3 flex gap-2">
          {hasSubmit && (
            <button
              onClick={() => onAction?.('submit_answer')}
              className="flex items-center gap-1.5 rounded-lg border border-[#6c63ff]/40 bg-[#6c63ff]/15 px-2.5 py-1.5 font-mono text-[10.5px] text-[#b9b3ff] transition-colors hover:bg-[#6c63ff]/25"
            >
              <Send size={12} /> ta réponse
            </button>
          )}
          {hasHint && (
            <button
              onClick={() => onAction?.('request_hint')}
              className="flex items-center gap-1.5 rounded-lg border border-[#26323d] bg-[#18212b] px-2.5 py-1.5 font-mono text-[10.5px] text-[#94a3b8] transition-colors hover:text-[#f5f7fa]"
            >
              <HelpCircle size={12} /> un indice
            </button>
          )}
        </div>
      )}
    </motion.div>
  );
}
