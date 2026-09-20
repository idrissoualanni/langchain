// ErrorCard V6.7 — erreur utilisateur-visible (§5 ADDENDUM).
// Message propre : jamais stack trace / chemin serveur / secret.
// Le texte de l'erreur est rendu par le part text officiel ;
// cette carte marque visuellement le type de réponse.
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';

export function ErrorCard() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2 rounded-[var(--radius-surface)] border border-destructive/25 bg-destructive/[0.05] px-3.5 py-2.5"
    >
      <AlertTriangle size={14} className="text-destructive" />
      <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-destructive uppercase">
        erreur
      </span>
    </motion.div>
  );
}
