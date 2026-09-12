// ErrorCard V6.7 — erreur utilisateur-visible (§5 ADDENDUM).
// Message propre : jamais stack trace / chemin serveur / secret.
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';

export function ErrorCard({ message }: { message: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#ef4444]/25 bg-[#ef4444]/[0.05] p-3.5"
    >
      <div className="mb-2 flex items-center gap-2">
        <AlertTriangle size={14} className="text-[#ef4444]" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[#ef4444]">
          erreur
        </span>
      </div>
      <div className="text-[13.5px] leading-relaxed text-[#f5f7fa]/90">
        {message}
      </div>
    </motion.div>
  );
}
