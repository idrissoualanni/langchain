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
    badge: 'bg-destructive]/15 text-destructive] border-destructive]/30',
  },
  warning: {
    icon: '⚠',
    badge: 'bg-warning]/15 text-warning] border-warning]/30',
  },
  info: {
    icon: 'ℹ',
    badge: 'bg-live]/15 text-live] border-live]/30',
  },
};

export function CodeAnalysisPanel({ analysis }: CodeAnalysisPanelProps) {
  return (
    <div className="flex h-full flex-col gap-3">
      {/* Résultat d'analyse structuré (tool analyze_code) */}
      {analysis ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <FileSearch size={13} className="text-live]" strokeWidth={1.8} />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground]">
              analyse · {analysis.status}
            </span>
            {analysis.issues.length > 0 && (
              <span className="rounded bg-card] px-1.5 py-0.5 font-mono text-[9px] text-foreground]/70">
                {analysis.issues.length} observation{analysis.issues.length > 1 ? 's' : ''}
              </span>
            )}
          </div>

          {analysis.issues.length === 0 ? (
            <div className="rounded-lg border border-success]/30 bg-success]/10 px-3 py-3 font-mono text-[11px] leading-relaxed text-success]">
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
                    className="flex items-start gap-2 rounded-lg border border-border] bg-muted] px-2.5 py-2"
                  >
                    <span
                      className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${tone.badge}`}
                    >
                      {tone.icon} {issue.severity}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-[10px] text-live]">
                        {issue.rule}
                      </div>
                      <div className="text-[11px] leading-relaxed text-foreground]/80">
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
            <FileSearch size={13} className="text-live]" strokeWidth={1.8} />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground]">
              analyse de code · règles détectées
            </span>
          </div>
          <p className="font-mono text-[10.5px] leading-relaxed text-muted-foreground]">
            Demandez au tuteur d'analyser votre code dans le chat — voici
            ce qu'il détecte (analyze_code, §29) :
          </p>
          <ul className="space-y-1">
            {DETECTED_RULES.map((r) => {
              const tone = SEVERITY_TONES[r.severity];
              return (
                <li
                  key={r.rule}
                  className="flex items-start gap-2 rounded-lg border border-border] bg-muted] px-2.5 py-1.5"
                >
                  <span
                    className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${tone.badge}`}
                  >
                    {tone.icon} {r.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-[10px] text-live]">
                      {r.rule}
                    </span>
                    <span className="text-[11px] leading-relaxed text-foreground]/75">
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
      <div className="mt-auto flex items-start gap-2 rounded-lg border border-live]/25 bg-live]/10 px-3 py-2.5">
        <GraduationCap size={14} className="mt-0.5 shrink-0 text-live]" strokeWidth={1.8} />
        <p className="font-mono text-[10.5px] leading-relaxed text-foreground]/75">
          Le tuteur ne corrige jamais le code à votre place : il
          identifie le problème, questionne, oriente avec un indice —
          c'est vous qui corrigez et réexécutez.
        </p>
      </div>
    </div>
  );
}
