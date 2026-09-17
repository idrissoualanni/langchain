// ExerciseCard V6.7 — exercice en attente de réponse (§20).
// Réutilise le style projet ; actions submit/hint pour le chat.
// Le texte de la réponse est rendu par le part text officiel
// (MarkdownText assistant-ui) — la carte n'affiche que le chrome
// et les actions structurées (aucune duplication de texte).
import { motion } from 'framer-motion';
import { Dumbbell, HelpCircle, Send } from 'lucide-react';
import type { ExerciseData } from '../../types/agentResponse';

export function ExerciseCard({
  data,
  actions,
  onAction,
}: {
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
      className="rounded-[var(--radius-surface)] border border-live/25 bg-live/[0.06] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <Dumbbell size={14} className="text-live" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-live uppercase">
          exercice
          {data.topic ? ` · ${data.topic}` : ''}
        </span>
      </div>
      {(hasSubmit || hasHint) && (
        <div className="flex gap-2">
          {hasSubmit && (
            <button
              onClick={() => onAction?.('submit_answer')}
              className="flex items-center gap-1.5 rounded-[var(--radius-control)] border border-live/40 bg-live/15 px-2.5 py-1.5 font-mono text-[10.5px] text-live transition-colors hover:bg-live/25"
            >
              <Send size={12} /> ta réponse
            </button>
          )}
          {hasHint && (
            <button
              onClick={() => onAction?.('request_hint')}
              className="flex items-center gap-1.5 rounded-[var(--radius-control)] border border-border bg-muted px-2.5 py-1.5 font-mono text-[10.5px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <HelpCircle size={12} /> un indice
            </button>
          )}
        </div>
      )}
    </motion.div>
  );
}
