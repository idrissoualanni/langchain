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
  supported: 'bg-[#22c55e]/15 text-[#22c55e] border-[#22c55e]/30',
  ambiguous: 'bg-[#f59e0b]/15 text-[#f59e0b] border-[#f59e0b]/30',
  unsupported: 'bg-[#f59e0b]/15 text-[#f59e0b] border-[#f59e0b]/30',
  unknown: 'bg-[#94a3b8]/15 text-[#94a3b8] border-[#94a3b8]/30',
  multi_domain: 'bg-[#6c63ff]/15 text-[#6c63ff] border-[#6c63ff]/30',
};

const KNOWLEDGE_TONES: Record<string, string> = {
  found: 'text-[#22c55e]',
  insufficient: 'text-[#f59e0b]',
  unavailable: 'text-[#94a3b8]',
};

const SEARCH_TONES: Record<string, string> = {
  found: 'text-[#22c55e]',
  insufficient: 'text-[#f59e0b]',
  unavailable: 'text-[#94a3b8]',
  error: 'text-[#ef4444]',
};

// V6.8 §54 — couleurs de statut budget
const BUDGET_TONES: Record<string, string> = {
  ok: 'text-[#22c55e]',
  near_limit: 'text-[#f59e0b]',
  compressed: 'text-[#f59e0b]',
  exceeded: 'text-[#ef4444]',
  unknown: 'text-[#94a3b8]',
};

// V6.6 §54 — couleurs d'action fallback
const FALLBACK_TONES: Record<string, string> = {
  use_local_knowledge: 'text-[#22c55e]',
  use_web_search: 'text-[#22d3ee]',
  ask_clarification: 'text-[#f59e0b]',
  use_general_tutor: 'text-[#94a3b8]',
  continue_without_external_search: 'text-[#94a3b8]',
};

// V7 §47 — couleurs d'action pédagogique (Learning Engine)
const STRATEGY_TONES: Record<string, string> = {
  answer: 'text-[#94a3b8]',
  explain: 'text-[#6c63ff]',
  practice: 'text-[#22c55e]',
  hint: 'text-[#22d3ee]',
  evaluate: 'text-[#f59e0b]',
  quiz: 'text-[#f59e0b]',
  review: 'text-[#f59e0b]',
  deepen: 'text-[#6c63ff]',
  advance_topic: 'text-[#22c55e]',
  clarify: 'text-[#f59e0b]',
  continue_activity: 'text-[#22d3ee]',
  complete_activity: 'text-[#22c55e]',
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
    <div className="rounded-lg border border-[#26323d] bg-[#18212b]">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#94a3b8]">
          {title}
          {badge && (
            <span className="rounded bg-[#111820] px-1.5 py-0.5 font-mono text-[9px] text-[#f5f7fa]/70">
              {badge}
            </span>
          )}
        </span>
        <ChevronDown
          size={13}
          className={`text-[#94a3b8]/60 transition-transform ${
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
            <div className="border-t border-[#26323d] px-3 py-2.5">
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
    <div className="rounded-xl border border-[#26323d] bg-[#111820]">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 border-b border-[#26323d] px-4 py-3">
        <Layers size={15} className="text-[#6c63ff]" strokeWidth={1.8} />
        <div>
          <div className="text-[13px] font-semibold tracking-tight text-[#f5f7fa]">
            Context Inspector
          </div>
          <div className="font-mono text-[10px] text-[#94a3b8]">
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
            className="min-w-0 flex-1 rounded-lg border border-[#26323d] bg-[#0b0f14] px-3 py-2 text-xs text-[#f5f7fa] placeholder:text-[#94a3b8]/40 focus:border-[#6c63ff]/50 focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={runPreview}
            disabled={!userId || loading || !query.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-[#6c63ff] px-3 py-2 font-mono text-[11px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
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
          <div className="rounded-lg border border-dashed border-[#26323d] py-6 text-center font-mono text-[11px] text-[#94a3b8]/60">
            Sélectionnez un utilisateur pour inspecter le contexte.
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-[#ef4444]/30 bg-[#ef4444]/10 px-3 py-2 font-mono text-[11px] text-[#ef4444]">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center gap-2 py-8 font-mono text-[11px] text-[#94a3b8]">
            <Loader2 size={14} className="animate-spin text-[#6c63ff]" />
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
            <div className="rounded-lg border border-[#26323d] bg-[#18212b] p-3">
              <div className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-[#94a3b8]">
                current subject
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11px]">
                <div className="text-[#94a3b8]/70">domain</div>
                <div className="truncate text-[#f5f7fa]">
                  {subject?.domain ?? '—'}
                </div>
                <div className="text-[#94a3b8]/70">subject</div>
                <div className="truncate text-[#f5f7fa]">
                  {subject?.name ?? router.subject ?? '—'}
                </div>
                <div className="text-[#94a3b8]/70">topic</div>
                <div className="truncate text-[#f5f7fa]">
                  {router.topic ?? '—'}
                </div>
                <div className="text-[#94a3b8]/70">confidence</div>
                <div className="text-[#6c63ff]">
                  {(router.confidence * 100).toFixed(0)}%
                </div>
                <div className="text-[#94a3b8]/70">status</div>
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
                        className="rounded bg-[#f59e0b]/15 px-1.5 py-0.5 font-mono text-[10px] text-[#f59e0b]"
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
                  <div className="text-[#f5f7fa]/85">
                    {subject.description}
                  </div>
                  {subject.teaching_style.length > 0 && (
                    <div className="text-[#94a3b8]">
                      style : {subject.teaching_style.join(', ')}
                    </div>
                  )}
                  {subject.pedagogical_guidelines.map((g, i) => (
                    <div key={i} className="text-[#94a3b8]">
                      - {g}
                    </div>
                  ))}
                  {subject.capabilities.length > 0 && (
                    <div className="pt-1 text-[#6c63ff]">
                      capabilities : {subject.capabilities.join(', ')}
                    </div>
                  )}
                </div>
              ) : (
                <div className="font-mono text-[10.5px] text-[#94a3b8]/60">
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
                    'text-[#94a3b8]'
                  }`}
                >
                  status : {preview.knowledge.status} · sources parcourues :{' '}
                  {preview.knowledge.searched_sources}
                </div>
                {preview.knowledge.items.map((item, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-[#26323d] bg-[#0b0f14] p-2.5"
                  >
                    <div className="flex items-center justify-between font-mono text-[10px]">
                      <span className="text-[#6c63ff]">
                        {item.source} / {item.topic}
                      </span>
                      <span className="text-[#94a3b8]">
                        {(item.relevance * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1.5 line-clamp-4 text-[11px] leading-relaxed text-[#f5f7fa]/75">
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
                      SEARCH_TONES[preview.web.status] ?? 'text-[#94a3b8]'
                    }`}
                  >
                    web : {preview.web.status} · query :{' '}
                    <span className="text-[#f5f7fa]/70">
                      {preview.web.query}
                    </span>
                  </div>
                  {preview.web.results.map((r, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-[#26323d] bg-[#0b0f14] p-2.5"
                    >
                      <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
                        <span className="min-w-0 truncate text-[#6c63ff]">
                          {r.title || r.source}
                        </span>
                        <span className="shrink-0 text-[#94a3b8]">
                          best {(r.relevance * 100).toFixed(0)}%
                        </span>
                      </div>
                      {r.url && (
                        <div className="mt-1 truncate font-mono text-[9.5px] text-[#94a3b8]/70">
                          {r.url}
                        </div>
                      )}
                      {r.snippet && (
                        <div className="mt-1.5 line-clamp-3 text-[11px] leading-relaxed text-[#f5f7fa]/75">
                          {r.snippet}
                        </div>
                      )}
                    </div>
                  ))}
                  {preview.web.results.length === 0 && (
                    <div className="rounded-lg border border-[#f59e0b]/30 bg-[#f59e0b]/10 px-2.5 py-2 font-mono text-[10.5px] text-[#f59e0b]">
                      Web search {preview.web.status}
                      <span className="text-[#94a3b8]">
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
                <div className="text-[#22c55e]">
                  disponibles : {preview.tools.available.join(', ') || '—'}
                </div>
                {preview.tools.unavailable.length > 0 && (
                  <div className="text-[#f59e0b]">
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
              <pre className="max-h-[280px] overflow-auto whitespace-pre-wrap rounded-lg bg-[#0b0f14] p-2.5 font-mono text-[10.5px] leading-relaxed text-[#f5f7fa]/80">
                {preview.user.text || '— vide —'}
              </pre>
            </Section>

            <Section
              title="thread context"
              badge={threadId ? threadId.slice(0, 8) : 'none'}
              open={openThread}
              onToggle={() => setOpenThread(!openThread)}
            >
              <pre className="whitespace-pre-wrap rounded-lg bg-[#0b0f14] p-2.5 font-mono text-[10.5px] leading-relaxed text-[#f5f7fa]/80">
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
                    <div className="text-[#f5f7fa]/85">
                      mastery :{' '}
                      {preview.learning.mastery === null
                        ? '— (jamais évalué)'
                        : `${Math.round(preview.learning.mastery * 100)}%`}
                      {preview.learning.confidence !== null && (
                        <span className="text-[#94a3b8]">
                          {' '}
                          (conf.{' '}
                          {Math.round(
                            preview.learning.confidence * 100
                          )}
                          %)
                        </span>
                      )}
                    </div>
                    <div className="text-[#94a3b8]">
                      attempts : {preview.learning.attempts}
                    </div>
                    {preview.learning.weak_points.length > 0 && (
                      <div className="text-[#f59e0b]">
                        weak :{' '}
                        {preview.learning.weak_points.join(', ')}
                      </div>
                    )}
                    {preview.learning.strengths.length > 0 && (
                      <div className="text-[#22c55e]">
                        strengths :{' '}
                        {preview.learning.strengths.join(', ')}
                      </div>
                    )}
                    {preview.learning.goal && (
                      <div className="text-[#6c63ff]">
                        goal : {preview.learning.goal.description}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="font-mono text-[10.5px] text-[#94a3b8]/60">
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
                  <div className="text-[#f5f7fa]/85">
                    {preview.budget.estimated_input_tokens != null
                      ? `${(preview.budget.estimated_input_tokens / 1000).toFixed(1)}k`
                      : '—'}{' '}
                    <span className="text-[#94a3b8]">/</span>{' '}
                    {preview.budget.context_window != null
                      ? `${(preview.budget.context_window / 1000).toFixed(0)}k window`
                      : 'window ? (inconnue)'}
                    <span
                      className={
                        BUDGET_TONES[
                          preview.budget.budget_status
                        ] ?? 'text-[#94a3b8]'
                      }
                    >
                      {' '}
                      · {preview.budget.budget_status}
                    </span>
                  </div>
                  <div className="text-[#94a3b8]">
                    output réservé :{' '}
                    {preview.budget.reserved_output_tokens} tok ·
                    available :{' '}
                    {preview.budget.available_input_tokens != null
                      ? `${preview.budget.available_input_tokens}`
                      : 'assumé (fallback conservateur)'}
                  </div>
                  <div className="text-[#94a3b8]">
                    sources : {preview.budget.sources_used} used ·{' '}
                    {preview.budget.sources_dropped} dropped
                    {preview.budget.sources_dropped > 0 && (
                      <span className="text-[#f59e0b]">
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
                  <div className="text-[#f5f7fa]/85">
                    action :{' '}
                    <span
                      className={
                        FALLBACK_TONES[
                          preview.fallback.action
                        ] ?? 'text-[#94a3b8]'
                      }
                    >
                      {preview.fallback.action}
                    </span>
                  </div>
                  <div
                    className="text-[#94a3b8]"
                    title={preview.fallback.reason}
                  >
                    raison :{' '}
                    {preview.fallback.reason.length > 90
                      ? `${preview.fallback.reason.slice(0, 90)}…`
                      : preview.fallback.reason}
                  </div>
                  <div className="text-[#94a3b8]">
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
                          className="rounded bg-[#111820] px-1.5 py-0.5 text-[9.5px] text-[#a5f3fc]"
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
                  <div className="text-[#f5f7fa]/85">
                    action :{' '}
                    <span
                      className={
                        STRATEGY_TONES[
                          preview.learning_strategy.action
                        ] ?? 'text-[#94a3b8]'
                      }
                    >
                      {preview.learning_strategy.action}
                    </span>
                    {(preview.learning_strategy.subject ||
                      preview.learning_strategy.topic) && (
                      <span className="text-[#94a3b8]">
                        {' '}
                        · {preview.learning_strategy.subject ?? '?'}/
                        {preview.learning_strategy.topic ?? '?'}
                      </span>
                    )}
                  </div>
                  <div className="text-[#94a3b8]">
                    raison :{' '}
                    {preview.learning_strategy.reason.length > 110
                      ? `${preview.learning_strategy.reason.slice(0, 110)}…`
                      : preview.learning_strategy.reason}
                  </div>
                  <div className="text-[#94a3b8]">
                    conf.{' '}
                    {Math.round(
                      preview.learning_strategy.confidence * 100
                    )}
                    % · priorité{' '}
                    {preview.learning_strategy.priority}/10
                  </div>
                  {preview.learning_strategy.recommended_tool && (
                    <div className="text-[#6c63ff]">
                      outil recommandé :{' '}
                      {preview.learning_strategy.recommended_tool}
                      <span className="text-[#94a3b8]">
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
              <pre className="max-h-[400px] overflow-auto whitespace-pre-wrap rounded-lg bg-[#0b0f14] p-2.5 font-mono text-[10px] leading-relaxed text-[#94a3b8]">
                {preview.prompt_preview}
              </pre>
            </Section>
          </motion.div>
        )}
      </div>
    </div>
  );
}
