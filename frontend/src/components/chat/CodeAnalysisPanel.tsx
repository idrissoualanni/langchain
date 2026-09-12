// CodeAnalysisPanel V5.2 — aide à l'analyse du code étudiant
//
// Affiche le résultat d'analyse structuré du tool analyze_code
// (§29-§30) SI fourni ; sinon, un état d'aide listant ce que le
// tuteur détecte — avec le principe pédagogique fondamental :
// le tuteur N'ÉCRIT JAMAIS le code à la place de l'étudiant (§31).
// Il identifie, questionne, oriente — l'étudiant corrige.
import { FileSearch, GraduationCap } from 'lucide-react';

export interface CodeAnalysisIssue {
  rule: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
}

export interface CodeAnalysisData {
  status: string;
  issues: CodeAnalysisIssue[];
}

interface CodeAnalysisPanelProps {
  analysis: CodeAnalysisData | null;
}

/** Règles détectées par analyze_code (app/agent/code_tools.py) —
 * illustrées pour l'étudiant tant qu'aucune analyse réelle n'est
 * fournie. */
const DETECTED_RULES: Array<{ rule: string; severity: CodeAnalysisIssue['severity']; description: string }> = [
  {
    rule: 'syntax',
    severity: 'error',
    description: 'Erreur de syntaxe (ligne + message de l\'interpréteur)',
  },
  {
    rule: 'print_vs_return',
    severity: 'warning',
    description: 'print() affiche sans renvoyer — vérifier la consigne (retour attendu ?)',
  },
  {
    rule: 'bare_except',
    severity: 'warning',
    description: 'except nu (sans type d\'exception) masque les erreurs',
  },
  {
    rule: 'while_true',
    severity: 'warning',
    description: 'while True sans condition d\'arrêt visible — risque de boucle infinie',
  },
  {
    rule: 'mutable_default',
    severity: 'warning',
    description: 'Valeur par défaut mutable (liste vide) — préférer None',
  },
  {
    rule: 'tabs',
    severity: 'info',
    description: 'Tabulations détectées — PEP 8 recommande 4 espaces',
  },
];

const SEVERITY_TONES: Record<CodeAnalysisIssue['severity'], { icon: string; badge: string }> = {
  error: {
    icon: '✗',
    badge: 'bg-[#ef4444]/15 text-[#ef4444] border-[#ef4444]/30',
  },
  warning: {
    icon: '⚠',
    badge: 'bg-[#f59e0b]/15 text-[#f59e0b] border-[#f59e0b]/30',
  },
  info: {
    icon: 'ℹ',
    badge: 'bg-[#6c63ff]/15 text-[#6c63ff] border-[#6c63ff]/30',
  },
};

export function CodeAnalysisPanel({ analysis }: CodeAnalysisPanelProps) {
  return (
    <div className="flex h-full flex-col gap-3">
      {/* Résultat d'analyse structuré (tool analyze_code) */}
      {analysis ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <FileSearch size={13} className="text-[#6c63ff]" strokeWidth={1.8} />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]">
              analyse · {analysis.status}
            </span>
            {analysis.issues.length > 0 && (
              <span className="rounded bg-[#111820] px-1.5 py-0.5 font-mono text-[9px] text-[#f5f7fa]/70">
                {analysis.issues.length} observation{analysis.issues.length > 1 ? 's' : ''}
              </span>
            )}
          </div>

          {analysis.issues.length === 0 ? (
            <div className="rounded-lg border border-[#22c55e]/30 bg-[#22c55e]/10 px-3 py-3 font-mono text-[11px] leading-relaxed text-[#22c55e]">
              Aucun problème détecté — le code compile et suit les règles
              de style de base.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {analysis.issues.map((issue, i) => {
                const tone = SEVERITY_TONES[issue.severity];
                return (
                  <li
                    key={i}
                    className="flex items-start gap-2 rounded-lg border border-[#26323d] bg-[#18212b] px-2.5 py-2"
                  >
                    <span
                      className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${tone.badge}`}
                    >
                      {tone.icon} {issue.severity}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-[10px] text-[#6c63ff]">
                        {issue.rule}
                      </div>
                      <div className="text-[11px] leading-relaxed text-[#f5f7fa]/80">
                        {issue.message}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : (
        /* État d'aide V1 : ce que l'agent détecte (règles réelles) */
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <FileSearch size={13} className="text-[#6c63ff]" strokeWidth={1.8} />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]">
              analyse de code · règles détectées
            </span>
          </div>
          <p className="font-mono text-[10.5px] leading-relaxed text-[#94a3b8]">
            Demandez au tuteur d'analyser votre code dans le chat — voici
            ce qu'il détecte (analyze_code, §29) :
          </p>
          <ul className="space-y-1">
            {DETECTED_RULES.map((r) => {
              const tone = SEVERITY_TONES[r.severity];
              return (
                <li
                  key={r.rule}
                  className="flex items-start gap-2 rounded-lg border border-[#26323d] bg-[#18212b] px-2.5 py-1.5"
                >
                  <span
                    className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${tone.badge}`}
                  >
                    {tone.icon} {r.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-[10px] text-[#6c63ff]">
                      {r.rule}
                    </span>
                    <span className="text-[11px] leading-relaxed text-[#f5f7fa]/75">
                      {' — '}
                      {r.description}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Principe pédagogique permanent (§31) */}
      <div className="mt-auto flex items-start gap-2 rounded-lg border border-[#6c63ff]/25 bg-[#6c63ff]/10 px-3 py-2.5">
        <GraduationCap size={14} className="mt-0.5 shrink-0 text-[#6c63ff]" strokeWidth={1.8} />
        <p className="font-mono text-[10.5px] leading-relaxed text-[#f5f7fa]/75">
          Le tuteur ne corrige jamais le code à votre place : il
          identifie le problème, questionne, oriente avec un indice —
          c'est vous qui corrigez et réexécutez.
        </p>
      </div>
    </div>
  );
}
