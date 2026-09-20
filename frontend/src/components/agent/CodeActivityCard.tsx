// CodeActivityCard V6.7 — activité de code (§22).
// Réutilise le CodeEditor V5.2 existant (pas de duplication §28).
import { motion } from 'framer-motion';
import { Terminal } from 'lucide-react';
import { CodeEditor } from '../chat/CodeEditor';
import type { CodeData } from '../../types/agentResponse';

export function CodeActivityCard({
  data,
  threadId,
  userId,
}: {
  data: CodeData;
  threadId: string | null;
  userId: string | null;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2.5 rounded-[var(--radius-surface)] border border-border bg-card p-3.5"
    >
      <div className="flex items-center gap-2">
        <Terminal size={14} className="text-live" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-live uppercase">
          pratique du code · {data.language || 'python'}
        </span>
      </div>
      <CodeEditor
        threadId={threadId}
        userId={userId}
        initialCode={data.starter_code || ''}
      />
    </motion.div>
  );
}
