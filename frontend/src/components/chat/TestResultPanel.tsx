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
    badge: 'bg-success]/15 text-success] border-success]/30',
    icon: <CheckCircle2 size={12} strokeWidth={2} />,
  },
  error: {
    label: 'error',
    badge: 'bg-destructive]/15 text-destructive] border-destructive]/30',
    icon: <XCircle size={12} strokeWidth={2} />,
  },
  timeout: {
    label: 'timeout',
    badge: 'bg-warning]/15 text-warning] border-warning]/30',
    icon: <Clock size={12} strokeWidth={2} />,
  },
};

export function TestResultPanel({ result }: TestResultPanelProps) {
  const tone =
    STATUS_TONES[result.status] ?? {
      label: result.status,
      badge: 'bg-muted-foreground]/15 text-muted-foreground] border-muted-foreground]/30',
      icon: <Clock size={12} strokeWidth={2} />,
    };

  return (
    <div className="rounded-lg border border-border] bg-background]">
      {/* Barre de statut : badge + exit_code + durée */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border] px-3 py-2">
        <span
          className={`flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide ${tone.badge}`}
        >
          {tone.icon}
          {tone.label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground]">
          exit_code <span className="text-foreground]">{result.exit_code}</span>
        </span>
        <span className="font-mono text-[10px] text-muted-foreground]">
          durée <span className="text-foreground]">{result.duration_ms}ms</span>
        </span>
      </div>

      {/* Sorties réelles de la sandbox */}
      <div className="space-y-2 p-3">
        <div>
          <div className="mb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground]/70">
            stdout
          </div>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-black/60 p-2.5 font-mono text-[11px] leading-relaxed text-foreground]/85">
            {result.stdout || '(vide)'}
          </pre>
        </div>

        {result.stderr && (
          <div>
            <div className="mb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground]/70">
              stderr
            </div>
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-destructive]/5 p-2.5 font-mono text-[11px] leading-relaxed text-destructive]">
              {result.stderr}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
