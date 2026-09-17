// HintCard V6.7 — indice progressif (niveau affiché).
// Le texte de l'indice est rendu par le part text officiel ;
// cette carte n'affiche que le niveau structuré.
import { motion } from 'framer-motion';
import { Lightbulb } from 'lucide-react';
import type { HintData } from '../../types/agentResponse';

export function HintCard({ data }: { data: HintData }) {
  const level = data.hint_level ?? 0;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-[var(--radius-surface)] border border-warning/25 bg-warning/[0.05] p-3.5"
    >
      <div className="flex items-center gap-2">
        <Lightbulb size={14} className="text-warning" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-warning uppercase">
          indice · niveau {level + 1}
        </span>
        <span className="ml-auto flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className={`h-1.5 w-1.5 rounded-full ${
                i <= level ? 'bg-warning' : 'bg-border'
              }`}
            />
          ))}
        </span>
      </div>
    </motion.div>
  );
}
