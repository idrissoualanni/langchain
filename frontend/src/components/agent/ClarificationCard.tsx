// ClarificationCard V6.7 — demande de précision avec BOUTONS (§25).
// Le frontend utilise actions[].options — JAMAIS le parsing
// du texte (§18 interdit).
import { motion } from 'framer-motion';
import { HelpCircle } from 'lucide-react';
import type { AgentResponseAction } from '../../types/agentResponse';

export function ClarificationCard({
  actions,
  onAction,
}: {
  actions: AgentResponseAction[];
  onAction?: (option: string) => void;
}) {
  const select = actions.find((a) => a.type === 'select');
  const options = (select?.options as string[] | undefined) ?? [];
  if (options.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-[var(--radius-surface)] border border-live/25 bg-live/[0.05] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <HelpCircle size={14} className="text-live" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-live uppercase">
          clarification
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt}
            onClick={() => onAction?.(opt)}
            className="rounded-[var(--radius-control)] border border-live/30 bg-live/10 px-3 py-1.5 font-mono text-[11px] text-live transition-colors hover:bg-live/20"
          >
            {opt}
          </button>
        ))}
      </div>
    </motion.div>
  );
}
