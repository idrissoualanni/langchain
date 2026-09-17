// ActivityFeed V5.2 — fil chronologique de l'activité pédagogique du thread
//
// Source de vérité : GET /api/threads/{id}/activity (state LangGraph
// thread-local, §42). Chaque entrée est un événement RÉEL émis par
// les tools (ACTIVITY_*/QUIZ_*/CODE_*) — jamais fabriqué ici.
//
// Rafraîchissement : au montage/changement de thread + bouton
// RefreshCw + polling léger 30s (page Memory — pas de polling
// agressif). Le résumé d'activité courante (ActivitySummary) est
// affiché en tête si une activité est active.
// Les réponses attendues ne sont JAMAIS affichées : le backend les
// exclut déjà de summarize_activity.
import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity as ActivityIcon,
  Brain,
  CheckCircle2,
  Clock,
  FileSearch,
  HelpCircle,
  Lightbulb,
  ListChecks,
  Loader2,
  MessageSquare,
  Play,
  RefreshCw,
  Terminal,
  Trophy,
  type LucideIcon,
} from 'lucide-react';
import type {
  ActivityLogEntry,
  ActivitySummary,
} from '../../types/activity';
import { getThreadActivity } from '../../api/activity';

interface ActivityFeedProps {
  userId: string | null;
  threadId: string | null;
}

/** Icône par événement backend (ACTIVITY_*, QUIZ_*, CODE_* — §33/§42). */
const EVENT_ICONS: Record<string, LucideIcon> = {
  ACTIVITY_STARTED: Play,
  ACTIVITY_WAITING: Clock,
  ACTIVITY_ANSWER_RECEIVED: MessageSquare,
  ACTIVITY_EVALUATED: CheckCircle2,
  ACTIVITY_HINT_REQUESTED: Lightbulb,
  ACTIVITY_UNDERSTANDING_ASSESSED: Brain,
  ACTIVITY_REVIEW_PROPOSED: ListChecks,
  QUIZ_STARTED: Play,
  QUIZ_QUESTION: HelpCircle,
  QUIZ_COMPLETED: Trophy,
  CODE_EXECUTION_START: Terminal,
  CODE_EXECUTION_END: Terminal,
  CODE_EXECUTION_ERROR: Terminal,
  CODE_TEST_START: Terminal,
  CODE_TEST_END: Terminal,
  CODE_TEST_ERROR: Terminal,
  CODE_ANALYSIS: FileSearch,
};

/** Libellé lisible par événement (fallback : l'event brut). */
const EVENT_LABELS: Record<string, string> = {
  ACTIVITY_STARTED: 'activité démarrée',
  ACTIVITY_WAITING: 'en attente de réponse',
  ACTIVITY_ANSWER_RECEIVED: 'réponse reçue',
  ACTIVITY_EVALUATED: 'réponse évaluée',
  ACTIVITY_HINT_REQUESTED: 'indice demandé',
  ACTIVITY_UNDERSTANDING_ASSESSED: 'compréhension évaluée',
  ACTIVITY_REVIEW_PROPOSED: 'révision proposée',
  QUIZ_STARTED: 'quiz démarré',
  QUIZ_QUESTION: 'question posée',
  QUIZ_COMPLETED: 'quiz terminé',
  CODE_EXECUTION_START: 'code lancé',
  CODE_EXECUTION_END: 'code exécuté',
  CODE_EXECUTION_ERROR: 'exécution refusée / en erreur',
  CODE_TEST_START: 'tests lancés',
  CODE_TEST_END: 'tests terminés',
  CODE_TEST_ERROR: 'tests en erreur',
  CODE_ANALYSIS: 'code analysé',
};

/** Ton de couleur du badge status (statuts réels du backend). */
function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (
    s.includes('error') ||
    s.includes('reject') ||
    s.includes('abandoned') ||
    s.includes('failed')
  ) {
    return 'bg-destructive]/15 text-destructive] border-destructive]/30';
  }
  if (
    s === 'completed' ||
    s === 'success' ||
    s === 'correct' ||
    s === 'done' ||
    s === 'good'
  ) {
    return 'bg-success]/15 text-success] border-success]/30';
  }
  if (
    s.includes('waiting') ||
    s.includes('hint') ||
    s.includes('timeout') ||
    s.includes('partial') ||
    s.includes('retry')
  ) {
    return 'bg-warning]/15 text-warning] border-warning]/30';
  }
  return 'bg-muted-foreground]/15 text-muted-foreground] border-muted-foreground]/30';
}

/** Badge de statut d'activité lisible. */
const STATUS_LABELS: Record<string, string> = {
  idle: 'idle',
  waiting_for_answer: 'en attente',
  evaluating: 'évaluation',
  giving_hint: 'indice',
  waiting_for_retry: 'nouvel essai',
  checking_understanding: 'vérification',
  completed: 'terminée',
  abandoned: 'abandonnée',
};

function formatTime(timestamp: string): string {
  // "2025-01-01T12:34:56" → "12:34:56" (timezone backend = local)
  return timestamp.split('T')[1]?.slice(0, 8) ?? '';
}

/** Résumé de l'activité courante (en tête du feed). */
function CurrentActivitySummaryCard({
  summary,
}: {
  summary: ActivitySummary;
}) {
  const isQuiz = summary.activity_type === 'quiz';
  const statusLabel =
    STATUS_LABELS[summary.status] ?? summary.status;
  const quiz = summary.quiz;
  const quizProgress = quiz
    ? `${Math.min(quiz.current_index + 1, quiz.total_questions)}/${quiz.total_questions} · score ${quiz.score}`
    : summary.total_questions > 0
      ? `${Math.min(summary.current_index + 1, summary.total_questions)}/${summary.total_questions} · score ${summary.score ?? 0}`
      : null;

  return (
    <div className="rounded-lg border border-live]/30 bg-live]/[0.07] p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-live]">
          activité en cours
        </span>
        <span
          className={`rounded border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${statusTone(summary.status)}`}
        >
          {statusLabel}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11px]">
        <div className="text-muted-foreground]/70">type</div>
        <div className="truncate text-foreground]">
          {summary.activity_type ?? '—'}
        </div>
        <div className="text-muted-foreground]/70">sujet</div>
        <div className="truncate text-foreground]">
          {summary.subject && summary.topic
            ? `${summary.subject}/${summary.topic}`
            : (summary.subject ?? summary.topic ?? '—')}
        </div>
        <div className="text-muted-foreground]/70">tentatives</div>
        <div className="text-foreground]">{summary.attempts}</div>
        {summary.hint_level > 0 && (
          <>
            <div className="text-muted-foreground]/70">indice</div>
            <div className="text-warning]">
              niveau {summary.hint_level}
            </div>
          </>
        )}
        {summary.expected_response_type && (
          <>
            <div className="text-muted-foreground]/70">réponse attendue</div>
            <div className="text-foreground]">
              {summary.expected_response_type}
            </div>
          </>
        )}
      </div>

      {/* Progression quiz si présente (jamais les réponses attendues) */}
      {isQuiz && quizProgress && (
        <div className="mt-2 flex items-center gap-1.5 rounded-md bg-background] px-2.5 py-1.5 font-mono text-[10.5px]">
          <Trophy size={11} className="text-warning]" />
          <span className="text-foreground]">{quizProgress}</span>
        </div>
      )}

      {summary.question_preview && (
        <div className="mt-2 line-clamp-2 rounded-md bg-background] px-2.5 py-1.5 text-[11px] leading-relaxed text-foreground]/80">
          {summary.question_preview}
        </div>
      )}
    </div>
  );
}

export function ActivityFeed({ userId, threadId }: ActivityFeedProps) {
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [log, setLog] = useState<ActivityLogEntry[]>([]);
  const [interactionCount, setInteractionCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeThread = useRef<string | null>(null);

  // Réf "dernier thread vu" — protège contre les réponses obsolètes
  // (assignée dans un effet, jamais pendant le render).
  useEffect(() => {
    activeThread.current = threadId;
  }, [threadId]);

  const refresh = useCallback(async () => {
    if (!userId || !threadId) {
      setSummary(null);
      setLog([]);
      setInteractionCount(0);
      setError(null);
      return;
    }
    setLoading(true);
    try {
      const res = await getThreadActivity(threadId, userId);
      // Le thread a pu changer pendant la requête — on ignore la réponse obsolète
      if (activeThread.current !== threadId) return;
      setSummary(res.activity);
      setLog(res.activity_log);
      setInteractionCount(res.interaction_count);
      setError(null);
    } catch (exc) {
      if (activeThread.current !== threadId) return;
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      if (activeThread.current === threadId) setLoading(false);
    }
  }, [userId, threadId]);

  // Chargement au montage + à chaque changement de thread/user
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Polling léger 30s (page Memory — refresh doux, pas agressif)
  useEffect(() => {
    if (!userId || !threadId) return;
    const id = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(id);
  }, [refresh, userId, threadId]);

  // ----- État vide : pas de thread (le feed est thread-scoped §50) -----
  if (!threadId) {
    return (
      <div className="rounded-lg border border-dashed border-border] px-3 py-8 text-center">
        <ActivityIcon size={24} className="mx-auto mb-2 text-muted-foreground]/30" />
        <p className="font-mono text-[11px] text-muted-foreground]">
          Sélectionnez un thread pour voir son fil d'activité.
        </p>
        <p className="mt-1 font-mono text-[10px] text-muted-foreground]/50">
          l'activité pédagogique est attachée au thread courant (§50)
        </p>
      </div>
    );
  }

  const hasActiveActivity =
    summary !== null &&
    summary.activity_type !== null &&
    summary.status !== 'idle';

  return (
    <div className="space-y-3">
      {/* Résumé de l'activité courante (s'il y en a une active) */}
      {summary && hasActiveActivity && (
        <CurrentActivitySummaryCard summary={summary} />
      )}

      {/* Erreur API (403 isolation, thread supprimé, réseau…) */}
      {error && (
        <div className="rounded-lg border border-destructive]/30 bg-destructive]/10 px-3 py-2 font-mono text-[11px] text-destructive]">
          {error}
        </div>
      )}

      {/* Fil chronologique */}
      <div className="flex min-h-0 flex-col">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground]">
            journal d'activité · {log.length} événement{log.length > 1 ? 's' : ''}
          </span>
          <span className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground]/50">
              {interactionCount} interaction{interactionCount > 1 ? 's' : ''}
            </span>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading || !userId || !threadId}
              className="flex items-center gap-1.5 rounded-md border border-border] bg-muted] px-2.5 py-1 font-mono text-[10px] text-muted-foreground] transition-colors hover:text-foreground] disabled:opacity-40"
              title="Rafraîchir l'activité du thread (30s auto)"
            >
              <RefreshCw
                size={11}
                className={loading ? 'animate-spin' : ''}
              />
              refresh
            </button>
          </span>
        </div>

        <div className="max-h-[380px] overflow-y-auto pr-1">
          {loading && log.length === 0 ? (
            <div className="flex items-center justify-center gap-2 py-8 font-mono text-[11px] text-muted-foreground]">
              <Loader2 size={13} className="animate-spin text-live]" />
              chargement de l'activité…
            </div>
          ) : log.length === 0 ? (
            <div className="py-8 text-center font-mono text-[11px] text-muted-foreground]/60">
              Aucune activité pédagogique dans ce thread — demandez un
              exercice, un quiz ou une vérification de compréhension
              au tuteur.
            </div>
          ) : (
            <div className="space-y-0">
              {log.map((entry, i) => {
                const Icon =
                  EVENT_ICONS[entry.event] ?? ActivityIcon;
                const label =
                  EVENT_LABELS[entry.event] ?? entry.event;
                const time = formatTime(entry.timestamp);
                return (
                  <motion.div
                    key={`${entry.timestamp}-${entry.event}-${i}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.16 }}
                    className="relative flex gap-2.5 py-1.5"
                  >
                    {/* Colonne vertébrale chronologique */}
                    {i < log.length - 1 && (
                      <div className="absolute left-[5px] top-7 h-full w-px bg-border]" />
                    )}
                    <div className="relative mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md border border-border] bg-muted]">
                      <Icon size={11} className="text-live]" strokeWidth={2} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <span className="font-mono text-[10px] text-muted-foreground]/50">
                          {time}
                        </span>
                        <span className="font-mono text-[11px] font-semibold text-foreground]/90">
                          {label}
                        </span>
                        {entry.status && (
                          <span
                            className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${statusTone(entry.status)}`}
                          >
                            {entry.status}
                          </span>
                        )}
                      </div>
                      {entry.detail && (
                        <div className="mt-0.5 line-clamp-2 font-mono text-[10px] leading-relaxed text-muted-foreground]/80">
                          {entry.detail}
                        </div>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
