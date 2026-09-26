// ContextInspectorCard V4 — Current Subject + inspection du contexte dynamique
//
// Outil dev pédagogique (§36/§37) : montre comment le Context Builder
// assemble le prompt — Router → Subject Config → Knowledge → Tools →
// User Memory → Thread. Sections extensibles, chaque source séparée.
// Signature visuelle : cohérente avec LongTermMemoryCard (surface sombre,
// mono pour la machine, badges de statut colorés par routing status).
import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ChevronDown,
  Layers,
  Loader2,
  Search,
} from 'lucide-react';
import type { ContextPreview, RouterStatus } from '../../types/agent';
import { previewContext } from '../../api/subjects';

interface ContextInspectorCardProps {
  userId: string | null;
  threadId: string | null;
}

const STATUS_TONES: Record<RouterStatus, string> = {
  supported: 'bg-success/15 text-success border-success/30',
  ambiguous: 'bg-warning/15 text-warning border-warning/30',
  unsupported: 'bg-warning/15 text-warning border-warning/30',
  unknown: 'bg-muted-foreground/15 text-muted-foreground border-muted-foreground/30',
  multi_domain: 'bg-live/15 text-live border-live/30',
};

const KNOWLEDGE_TONES: Record<string, string> = {
  found: 'text-success',
  insufficient: 'text-warning',
  unavailable: 'text-muted-foreground',
};

const SEARCH_TONES: Record<string, string> = {
  found: 'text-success',
  insufficient: 'text-warning',
  unavailable: 'text-muted-foreground',
  error: 'text-destructive',
};

// V6.8 §54 — couleurs de statut budget
const BUDGET_TONES: Record<string, string> = {
  ok: 'text-success',
  near_limit: 'text-warning',
  compressed: 'text-warning',
  exceeded: 'text-destructive',
  unknown: 'text-muted-foreground',
};

// V6.6 §54 — couleurs d'action fallback
const FALLBACK_TONES: Record<string, string> = {
  use_local_knowledge: 'text-success',
  use_web_search: 'text-live',
  ask_clarification: 'text-warning',
  use_general_tutor: 'text-muted-foreground',
  continue_without_external_search: 'text-muted-foreground',
};

// V7 §47 — couleurs d'action pédagogique (Learning Engine)
const STRATEGY_TONES: Record<string, string> = {
  answer: 'text-muted-foreground',
  explain: 'text-live',
  practice: 'text-success',
  hint: 'text-live',
  evaluate: 'text-warning',
  quiz: 'text-warning',
  review: 'text-warning',
  deepen: 'text-live',
  advance_topic: 'text-success',
  clarify: 'text-warning',
  continue_activity: 'text-live',
  complete_activity: 'text-success',
};

function Section({
  title,
  open,
  onToggle,
  children,
  badge,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  badge?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {title}
          {badge && (
            <span className="rounded bg-card px-1.5 py-0.5 font-mono text-[9px] text-foreground/70">
              {badge}
            </span>
          )}
        </span>
        <ChevronDown
          size={13}
          className={`text-muted-foreground transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="border-t border-border px-3 py-2.5">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ContextInspectorCard({
  userId,
  threadId,
}: ContextInspectorCardProps) {
  const [query, setQuery] = useState(
    'Explique-moi les fonctions Python.'
  );
  const [preview, setPreview] = useState<ContextPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [openUser, setOpenUser] = useState(false);
  const [openThread, setOpenThread] = useState(false);
  const [openSubject, setOpenSubject] = useState(false);
  const [openKnowledge, setOpenKnowledge] = useState(true);
  const [openSearch, setOpenSearch] = useState(false);
  const [openTools, setOpenTools] = useState(false);
  const [openPrompt, setOpenPrompt] = useState(false);
  const [openLearning, setOpenLearning] = useState(false);
  const [openBudget, setOpenBudget] = useState(false);
  const [openFallback, setOpenFallback] = useState(false);
  const [openStrategy, setOpenStrategy] = useState(false);

  const runPreview = async () => {
    if (!userId || !query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await previewContext({
        user_id: userId,
        thread_id: threadId ?? undefined,
        query: query.trim(),
      });
      setPreview(result);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
      setPreview(null);
    } finally {
      setLoading(false);
    }
  };

  const router = preview?.router;
  const subject = preview?.subject ?? null;

  return (
    <div className="rounded-xl border border-border bg-card">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <Layers size={15} className="text-live" strokeWidth={1.8} />
        <div>
          <div className="text-[13px] font-semibold tracking-tight text-foreground">
            Context Inspector
          </div>
          <div className="font-mono text-[10px] text-muted-foreground">
            routing · context · prompt
          </div>
        </div>
        {preview && router && (
          <div className="ml-auto flex items-center gap-2">
            <span
              className={`rounded-md border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wide ${
                STATUS_TONES[router.status]
              }`}
            >
              {router.status}
            </span>
          </div>
        )}
      </div>

      <div className="space-y-3 p-4">
        {/* Barre de requête */}
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runPreview()}
            disabled={!userId || loading}
            placeholder="Question à router…"
            className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/40 focus:border-live/50 focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={runPreview}
            disabled={!userId || loading || !query.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-live px-3 py-2 font-mono text-[11px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Search size={13} />
            )}
            preview
          </button>
        </div>

        {!userId && (
          <div className="rounded-lg border border-dashed border-border py-6 text-center font-mono text-[11px] text-muted-foreground">
            Sélectionnez un utilisateur pour inspecter le contexte.
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 font-mono text-[11px] text-destructive">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center gap-2 py-8 font-mono text-[11px] text-muted-foreground">
            <Loader2 size={14} className="animate-spin text-live" />
            routing → context → prompt…
          </div>
        )}

        {preview && router && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-3"
          >
            {/* Current Subject — Domain/Subject/Topic/Confidence/Status */}
            <div className="rounded-lg border border-border bg-muted p-3">
              <div className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                current subject
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11px]">
                <div className="text-muted-foreground">domain</div>
                <div className="truncate text-foreground">
                  {subject?.domain ?? '—'}
                </div>
                <div className="text-muted-foreground">subject</div>
                <div className="truncate text-foreground">
                  {subject?.name ?? router.subject ?? '—'}
                </div>
                <div className="text-muted-foreground">topic</div>
                <div className="truncate text-foreground">
                  {router.topic ?? '—'}
                </div>
                <div className="text-muted-foreground">confidence</div>
                <div className="text-live">
                  {(router.confidence * 100).toFixed(0)}%
                </div>
                <div className="text-muted-foreground">status</div>
                <div>
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                      STATUS_TONES[router.status]
                    }`}
                  >
                    {router.status}
                  </span>
                </div>
              </div>
              {router.status === 'ambiguous' &&
                router.candidates.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {router.candidates.map((c) => (
                      <span
                        key={c}
                        className="rounded bg-warning/15 px-1.5 py-0.5 font-mono text-[10px] text-warning"
                      >
                        ? {c}
                      </span>
                    ))}
                  </div>
                )}
            </div>

            {/* Sections extensibles — une par source de contexte */}
            <Section
              title="subject context"
              badge={subject ? subject.id : 'none'}
              open={openSubject}
              onToggle={() => setOpenSubject(!openSubject)}
            >
              {subject ? (
                <div className="space-y-1.5 font-mono text-[10.5px]">
                  <div className="text-foreground/85">
                    {subject.description}
                  </div>
                  {subject.teaching_style.length > 0 && (
                    <div className="text-muted-foreground">
                      style : {subject.teaching_style.join(', ')}
                    </div>
                  )}
                  {subject.pedagogical_guidelines.map((g, i) => (
                    <div key={i} className="text-muted-foreground">
                      - {g}
                    </div>
                  ))}
                  {subject.capabilities.length > 0 && (
                    <div className="pt-1 text-live">
                      capabilities : {subject.capabilities.join(', ')}
                    </div>
                  )}
                </div>
              ) : (
                <div className="font-mono text-[10.5px] text-muted-foreground">
                  Aucune matière sélectionnée (tuteur général).
                </div>
              )}
            </Section>

            <Section
              title="knowledge"
              badge={
                preview.knowledge.status +
                (preview.knowledge.items.length
                  ? ` · ${preview.knowledge.items.length}`
                  : '')
              }
              open={openKnowledge}
              onToggle={() => setOpenKnowledge(!openKnowledge)}
            >
              <div className="space-y-2">
                <div
                  className={`font-mono text-[10.5px] ${
                    KNOWLEDGE_TONES[preview.knowledge.status] ??
                    'text-muted-foreground'
                  }`}
                >
                  status : {preview.knowledge.status} · sources parcourues :{' '}
                  {preview.knowledge.searched_sources}
                </div>
                {preview.knowledge.items.map((item, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-border bg-background p-2.5"
                  >
                    <div className="flex items-center justify-between font-mono text-[10px]">
                      <span className="text-live">
                        {item.source} / {item.topic}
                      </span>
                      <span className="text-muted-foreground">
                        {(item.relevance * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1.5 line-clamp-4 text-[11px] leading-relaxed text-foreground/75">
                      {item.content}
                    </div>
                  </div>
                ))}
              </div>
            </Section>

            {/* V6.5 §29 — Search Inspector (web fallback) */}
            {preview.web && preview.web.status !== 'unavailable' && (
              <Section
                title="search · web"
                badge={
                  preview.web.status +
                  (preview.web.results.length
                    ? ` · ${preview.web.results.length}`
                    : '')
                }
                open={openSearch}
                onToggle={() => setOpenSearch(!openSearch)}
              >
                <div className="space-y-2">
                  <div
                    className={`font-mono text-[10.5px] ${
                      SEARCH_TONES[preview.web.status] ?? 'text-muted-foreground'
                    }`}
                  >
                    web : {preview.web.status} · query :{' '}
                    <span className="text-foreground/70">
                      {preview.web.query}
                    </span>
                  </div>
                  {preview.web.results.map((r, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-border bg-background p-2.5"
                    >
                      <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
                        <span className="min-w-0 truncate text-live">
                          {r.title || r.source}
                        </span>
                        <span className="shrink-0 text-muted-foreground">
                          best {(r.relevance * 100).toFixed(0)}%
                        </span>
                      </div>
                      {r.url && (
                        <div className="mt-1 truncate font-mono text-[9.5px] text-muted-foreground">
                          {r.url}
                        </div>
                      )}
                      {r.snippet && (
                        <div className="mt-1.5 line-clamp-3 text-[11px] leading-relaxed text-foreground/75">
                          {r.snippet}
                        </div>
                      )}
                    </div>
                  ))}
                  {preview.web.results.length === 0 && (
                    <div className="rounded-lg border border-warning/30 bg-warning/10 px-2.5 py-2 font-mono text-[10.5px] text-warning">
                      Web search {preview.web.status}
                      <span className="text-muted-foreground">
                        {' '}
                        → fallback: General Tutor
                      </span>
                    </div>
                  )}
                </div>
              </Section>
            )}

            <Section
              title="tools"
              badge={`${preview.tools.available.length} dispo`}
              open={openTools}
              onToggle={() => setOpenTools(!openTools)}
            >
              <div className="space-y-1.5 font-mono text-[10.5px]">
                <div className="text-success">
                  disponibles : {preview.tools.available.join(', ') || '—'}
                </div>
                {preview.tools.unavailable.length > 0 && (
                  <div className="text-warning">
                    déclarés non enregistrés (non exposés au modèle) :{' '}
                    {preview.tools.unavailable.join(', ')}
                  </div>
                )}
              </div>
            </Section>

            <Section
              title="user context"
              badge={`${preview.stats.memories_used ?? 0} faits`}
              open={openUser}
              onToggle={() => setOpenUser(!openUser)}
            >
              <pre className="max-h-[280px] overflow-auto whitespace-pre-wrap rounded-lg bg-background p-2.5 font-mono text-[10.5px] leading-relaxed text-foreground/80">
                {preview.user.text || '— vide —'}
              </pre>
            </Section>

            <Section
              title="thread context"
              badge={threadId ? threadId.slice(0, 8) : 'none'}
              open={openThread}
              onToggle={() => setOpenThread(!openThread)}
            >
              <pre className="whitespace-pre-wrap rounded-lg bg-background p-2.5 font-mono text-[10.5px] leading-relaxed text-foreground/80">
                {preview.thread.text || '— vide —'}
              </pre>
            </Section>

            {/* V6 — Learning context sélectionné (source n°7) */}
            {preview.learning && (
              <Section
                title="learning"
                badge={
                  preview.learning.status === 'active'
                    ? `${preview.learning.subject}/${preview.learning.topic}`
                    : preview.learning.status
                }
                open={openLearning}
                onToggle={() => setOpenLearning(!openLearning)}
              >
                {preview.learning.status === 'active' ? (
                  <div className="space-y-1 font-mono text-[10.5px]">
                    <div className="text-foreground/85">
                      mastery :{' '}
                      {preview.learning.mastery === null
                        ? '— (jamais évalué)'
                        : `${Math.round(preview.learning.mastery * 100)}%`}
                      {preview.learning.confidence !== null && (
                        <span className="text-muted-foreground">
                          {' '}
                          (conf.{' '}
                          {Math.round(
                            preview.learning.confidence * 100
                          )}
                          %)
                        </span>
                      )}
                    </div>
                    <div className="text-muted-foreground">
                      attempts : {preview.learning.attempts}
                    </div>
                    {preview.learning.weak_points.length > 0 && (
                      <div className="text-warning">
                        weak :{' '}
                        {preview.learning.weak_points.join(', ')}
                      </div>
                    )}
                    {preview.learning.strengths.length > 0 && (
                      <div className="text-success">
                        strengths :{' '}
                        {preview.learning.strengths.join(', ')}
                      </div>
                    )}
                    {preview.learning.goal && (
                      <div className="text-live">
                        goal : {preview.learning.goal.description}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="font-mono text-[10.5px] text-muted-foreground">
                    {preview.learning.status === 'not_started'
                      ? 'Pas encore de progression suivie (cas normal).'
                      : 'Indisponible (erreur de lecture — fallback silencieux).'}
                  </div>
                )}
              </Section>
            )}

            {/* V6.8 §54 — Budget (interface développeur uniquement) */}
            {preview.budget && (
              <Section
                title="budget"
                badge={preview.budget.budget_status}
                open={openBudget}
                onToggle={() => setOpenBudget(!openBudget)}
              >
                <div className="space-y-1.5 font-mono text-[10.5px]">
                  <div className="text-foreground/85">
                    {preview.budget.estimated_input_tokens != null
                      ? `${(preview.budget.estimated_input_tokens / 1000).toFixed(1)}k`
                      : '—'}{' '}
                    <span className="text-muted-foreground">/</span>{' '}
                    {preview.budget.context_window != null
                      ? `${(preview.budget.context_window / 1000).toFixed(0)}k window`
                      : 'window ? (inconnue)'}
                    <span
                      className={
                        BUDGET_TONES[
                          preview.budget.budget_status
                        ] ?? 'text-muted-foreground'
                      }
                    >
                      {' '}
                      · {preview.budget.budget_status}
                    </span>
                  </div>
                  <div className="text-muted-foreground">
                    output réservé :{' '}
                    {preview.budget.reserved_output_tokens} tok ·
                    available :{' '}
                    {preview.budget.available_input_tokens != null
                      ? `${preview.budget.available_input_tokens}`
                      : 'assumé (fallback conservateur)'}
                  </div>
                  <div className="text-muted-foreground">
                    sources : {preview.budget.sources_used} used ·{' '}
                    {preview.budget.sources_dropped} dropped
                    {preview.budget.sources_dropped > 0 && (
                      <span className="text-warning">
                        {' '}
                        (compression P4→P3→P2, P0 intact)
                      </span>
                    )}
                  </div>
                </div>
              </Section>
            )}

            {/* V6.6 §54/§55 — Fallback (raison, candidats — dev) */}
            {preview.fallback && (
              <Section
                title="fallback"
                badge={preview.fallback.action}
                open={openFallback}
                onToggle={() => setOpenFallback(!openFallback)}
              >
                <div className="space-y-1.5 font-mono text-[10.5px]">
                  <div className="text-foreground/85">
                    action :{' '}
                    <span
                      className={
                        FALLBACK_TONES[
                          preview.fallback.action
                        ] ?? 'text-muted-foreground'
                      }
                    >
                      {preview.fallback.action}
                    </span>
                  </div>
                  <div
                    className="text-muted-foreground"
                    title={preview.fallback.reason}
                  >
                    raison :{' '}
                    {preview.fallback.reason.length > 90
                      ? `${preview.fallback.reason.slice(0, 90)}…`
                      : preview.fallback.reason}
                  </div>
                  <div className="text-muted-foreground">
                    états : {preview.fallback.source_status || '—'} ·
                    conf.{' '}
                    {Math.round(
                      preview.fallback.confidence * 100
                    )}
                    %
                  </div>
                  {preview.fallback.candidates.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {preview.fallback.candidates.map((c) => (
                        <span
                          key={c}
                          className="rounded bg-card px-1.5 py-0.5 text-[9.5px] text-live"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* V7 §47 — Learning Strategy (décision engine, dev) */}
            {preview.learning_strategy && (
              <Section
                title="learning strategy"
                badge={preview.learning_strategy.action}
                open={openStrategy}
                onToggle={() => setOpenStrategy(!openStrategy)}
              >
                <div className="space-y-1.5 font-mono text-[10.5px]">
                  <div className="text-foreground/85">
                    action :{' '}
                    <span
                      className={
                        STRATEGY_TONES[
                          preview.learning_strategy.action
                        ] ?? 'text-muted-foreground'
                      }
                    >
                      {preview.learning_strategy.action}
                    </span>
                    {(preview.learning_strategy.subject ||
                      preview.learning_strategy.topic) && (
                      <span className="text-muted-foreground">
                        {' '}
                        · {preview.learning_strategy.subject ?? '?'}/
                        {preview.learning_strategy.topic ?? '?'}
                      </span>
                    )}
                  </div>
                  <div className="text-muted-foreground">
                    raison :{' '}
                    {preview.learning_strategy.reason.length > 110
                      ? `${preview.learning_strategy.reason.slice(0, 110)}…`
                      : preview.learning_strategy.reason}
                  </div>
                  <div className="text-muted-foreground">
                    conf.{' '}
                    {Math.round(
                      preview.learning_strategy.confidence * 100
                    )}
                    % · priorité{' '}
                    {preview.learning_strategy.priority}/10
                  </div>
                  {preview.learning_strategy.recommended_tool && (
                    <div className="text-live">
                      outil recommandé :{' '}
                      {preview.learning_strategy.recommended_tool}
                      <span className="text-muted-foreground">
                        {' '}
                        (le tuteur choisit — jamais exécuté d'office)
                      </span>
                    </div>
                  )}
                </div>
              </Section>
            )}

            <Section
              title="prompt"
              badge={`${preview.prompt_preview.length} chars`}
              open={openPrompt}
              onToggle={() => setOpenPrompt(!openPrompt)}
            >
              <pre className="max-h-[400px] overflow-auto whitespace-pre-wrap rounded-lg bg-background p-2.5 font-mono text-[10px] leading-relaxed text-muted-foreground">
                {preview.prompt_preview}
              </pre>
            </Section>
          </motion.div>
        )}
      </div>
    </div>
  );
}
