// DiagramCard V6.7 — AgentResponse type='diagram'.
// Le backend fournit data.chart = code mermaid BRUT (jamais de bloc
// markdown, jamais de fence ```). Cette carte le rend via
// MermaidDiagram (SVG) dans le style des autres cartes pédagogiques.
// Sans chart exploitable → repli discret (le texte du message reste
// rendu par le part text officiel, l'UI ne casse jamais).
import { motion } from 'framer-motion';
import { Network } from 'lucide-react';
import type { DiagramData } from '../../types/agentResponse';
import { MermaidDiagram } from '../assistant-ui/elements/mermaid-diagram.aui';

export function DiagramCard({ data }: { data: DiagramData }) {
  const chart = typeof data?.chart === 'string' ? data.chart.trim() : '';
  if (!chart) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-[var(--radius-surface)] border border-live/25 bg-live/[0.05] p-3.5"
    >
      <div className="mb-1 flex items-center gap-2">
        <Network size={14} className="text-live" />
        <span className="font-mono text-[10px] font-semibold tracking-[0.14em] text-live uppercase">
          {data.caption || 'diagramme'}
        </span>
      </div>
      {/* MermaidDiagram applique ses propres bordures arrondies ;
          on neutralise le contour pour qu'il s'intègre à la carte. */}
      <div className="[&_.aui-mermaid-root]:border-0 [&_.aui-mermaid-root]:bg-transparent">
        <MermaidDiagram chart={chart} />
      </div>
    </motion.div>
  );
}
