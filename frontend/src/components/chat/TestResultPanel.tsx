// TestResultPanel V5.2 — panneau de résultat d'exécution CodeRunResult
//
// Affiche le résultat RÉEL de la sandbox backend (§24-§27) :
// status (badge coloré), stdout (noir mono préformaté), stderr
// (rouge), exit_code, duration_ms. Aucune simulation — ce panneau
// n'affiche que ce que /api/threads/{id}/run-code a retourné.
// Exporté séparément pour être réutilisé (CodeEditor, panneaux dev).
import { CheckCircle2, Clock, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import type { CodeRunResult } from '../../types/activity';

interface TestResultPanelProps {
  result: CodeRunResult;
}

const STATUS_TONES: Record<string, { label: string; badge: string; icon: ReactNode }> = {
  success: {
    label: 'success',
    badge: 'bg-[#22c55e]/15 text-[#22c55e] border-[#22c55e]/30',
    icon: <CheckCircle2 size={12} strokeWidth={2} />,
  },
  error: {
    label: 'error',
    badge: 'bg-[#ef4444]/15 text-[#ef4444] border-[#ef4444]/30',
    icon: <XCircle size={12} strokeWidth={2} />,
  },
  timeout: {
    label: 'timeout',
    badge: 'bg-[#f59e0b]/15 text-[#f59e0b] border-[#f59e0b]/30',
    icon: <Clock size={12} strokeWidth={2} />,
  },
};

export function TestResultPanel({ result }: TestResultPanelProps) {
  const tone =
    STATUS_TONES[result.status] ?? {
      label: result.status,
      badge: 'bg-[#94a3b8]/15 text-[#94a3b8] border-[#94a3b8]/30',
      icon: <Clock size={12} strokeWidth={2} />,
    };

  return (
    <div className="rounded-lg border border-[#26323d] bg-[#0b0f14]">
      {/* Barre de statut : badge + exit_code + durée */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-[#26323d] px-3 py-2">
        <span
          className={`flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide ${tone.badge}`}
        >
          {tone.icon}
          {tone.label}
        </span>
        <span className="font-mono text-[10px] text-[#94a3b8]">
          exit_code <span className="text-[#f5f7fa]">{result.exit_code}</span>
        </span>
        <span className="font-mono text-[10px] text-[#94a3b8]">
          durée <span className="text-[#f5f7fa]">{result.duration_ms}ms</span>
        </span>
      </div>

      {/* Sorties réelles de la sandbox */}
      <div className="space-y-2 p-3">
        <div>
          <div className="mb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]/70">
            stdout
          </div>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-black/60 p-2.5 font-mono text-[11px] leading-relaxed text-[#f5f7fa]/85">
            {result.stdout || '(vide)'}
          </pre>
        </div>

        {result.stderr && (
          <div>
            <div className="mb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]/70">
              stderr
            </div>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-[#ef4444]/5 p-2.5 font-mono text-[11px] leading-relaxed text-[#f87171]">
              {result.stderr}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
