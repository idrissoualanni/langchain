// CodeActivityCard V6.7 — activité de code (§22).
// Réutilise le CodeEditor V5.2 existant (pas de duplication §28).
import { motion } from 'framer-motion';
import { Terminal } from 'lucide-react';
import { CodeEditor } from '../chat/CodeEditor';
import type { CodeData } from '../../types/agentResponse';

export function CodeActivityCard({
  message,
  data,
  threadId,
  userId,
}: {
  message: string;
  data: CodeData;
  threadId: string | null;
  userId: string | null;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2.5 rounded-xl border border-[#26323d] bg-[#111820] p-3.5"
    >
      <div className="flex items-center gap-2">
        <Terminal size={14} className="text-[#22d3ee]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#22d3ee]">
          pratique du code · {data.language || 'python'}
        </span>
      </div>
      <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-[#f5f7fa]/85">
        {message}
      </div>
      <CodeEditor
        threadId={threadId}
        userId={userId}
        initialCode={data.starter_code || ''}
      />
    </motion.div>
  );
}
