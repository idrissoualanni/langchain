// ClarificationCard V6.7 — demande de précision avec BOUTONS (§25).
// Le frontend utilise actions[].options — JAMAIS le parsing
// du texte (§18 interdit).
import { motion } from 'framer-motion';
import { HelpCircle } from 'lucide-react';
import type { AgentResponseAction } from '../../types/agentResponse';

export function ClarificationCard({
  message,
  actions,
  onAction,
}: {
  message: string;
  actions: AgentResponseAction[];
  onAction?: (option: string) => void;
}) {
  const select = actions.find((a) => a.type === 'select');
  const options = (select?.options as string[] | undefined) ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#22d3ee]/25 bg-[#22d3ee]/[0.05] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <HelpCircle size={14} className="text-[#22d3ee]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#22d3ee]">
          clarification
        </span>
      </div>
      <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
      {options.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => onAction?.(opt)}
              className="rounded-lg border border-[#22d3ee]/30 bg-[#22d3ee]/10 px-3 py-1.5 font-mono text-[11px] text-[#a5f3fc] transition-colors hover:bg-[#22d3ee]/20"
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </motion.div>
  );
}
