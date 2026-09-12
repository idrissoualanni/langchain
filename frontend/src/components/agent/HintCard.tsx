// HintCard V6.7 — indice progressif (niveau affiché).
import { motion } from 'framer-motion';
import { Lightbulb } from 'lucide-react';
import type { HintData } from '../../types/agentResponse';

export function HintCard({
  message,
  data,
}: {
  message: string;
  data: HintData;
}) {
  const level = data.hint_level ?? 0;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#f59e0b]/25 bg-[#f59e0b]/[0.05] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <Lightbulb size={14} className="text-[#f59e0b]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#f59e0b]">
          indice · niveau {level + 1}
        </span>
        <span className="ml-auto flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className={`h-1.5 w-1.5 rounded-full ${
                i <= level ? 'bg-[#f59e0b]' : 'bg-[#26323d]'
              }`}
            />
          ))}
        </span>
      </div>
      <div className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
    </motion.div>
  );
}
