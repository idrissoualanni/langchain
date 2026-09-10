// MemoryPage — mémoire LangGraph : profil longue durée, stats, checkpoints, state
// La sélection user/thread se fait dans la sidebar ; cette page
// affiche le contexte actif en lecture seule.
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Braces, Clock, Database } from 'lucide-react';
import { useSelection } from '../hooks/useSelection';
import { useMemory } from '../hooks/useMemory';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { LongTermMemoryCard } from '../components/memory/LongTermMemoryCard';
import { ContextInspectorCard } from '../components/memory/ContextInspectorCard';

export function MemoryPage() {
  const { currentUser, currentThread } = useSelection();
  const {
    state,
    history,
    overview,
    loading,
    refresh,
    updateProfile,
    addFact,
    editFact,
    removeFact,
  } = useMemory(
    currentThread?.thread_id ?? null,
    currentUser?.user_id ?? null
  );

  const [showRaw, setShowRaw] = useState(false);

  const stats = [
    {
      label: 'user',
      value: state?.user_id ?? '—',
      mono: true,
      truncate: true,
    },
    {
      label: 'thread',
      value: state?.thread_id ?? currentThread?.thread_id ?? '—',
      mono: true,
      truncate: true,
    },
    {
      label: 'interactions',
      value: String(state?.interaction_count ?? 0),
    },
    {
      label: 'messages',
      value: String(state?.message_count ?? 0),
    },
    {
      label: 'checkpoints',
      value: String(history.length),
    },
  ];

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* En-tête */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[#f5f7fa]">
            <Database size={16} className="text-[#6c63ff]" strokeWidth={1.8} />
            Memory
          </h1>
          <p className="mt-0.5 font-mono text-[10px] text-[#94a3b8]">
            sqlite · checkpoints.db · langgraph state
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2 font-mono text-[11px]">
          {currentUser ? (
            <span className="max-w-[160px] truncate rounded-md bg-[#18212b] px-2 py-1 text-[#f5f7fa]/80">
              {currentUser.name}
            </span>
          ) : (
            <span className="rounded-md bg-[#18212b] px-2 py-1 text-[#94a3b8]/60">
              no user
            </span>
          )}
          <span className="text-[#94a3b8]/40">/</span>
          {currentThread ? (
            <span
              className="max-w-[200px] truncate rounded-md bg-[#18212b] px-2 py-1 text-[#f5f7fa]/80"
              title={currentThread.thread_id}
            >
              {currentThread.name}
            </span>
          ) : (
            <span className="rounded-md bg-[#18212b] px-2 py-1 text-[#94a3b8]/60">
              no thread
            </span>
          )}
        </div>
      </div>

      {!currentThread ? (
        <div className="space-y-5">
          {/* MemoryFacts — visible même sans thread (user-only) */}
          <LongTermMemoryCard
            overview={overview}
            loading={loading}
            onRefresh={refresh}
            onSaveProfile={updateProfile}
            onAddFact={addFact}
            onEditFact={editFact}
            onRemoveFact={removeFact}
            hasUser={Boolean(currentUser)}
          />
          {/* Context Inspector V4 — visible dès qu'un user existe */}
          <ContextInspectorCard
            userId={currentUser?.user_id ?? null}
            threadId={null}
          />
          <Card className="p-10 text-center">
            <Database size={32} className="mx-auto mb-3 text-[#94a3b8]/30" />
            <div className="text-sm text-[#94a3b8]">
              Sélectionnez un thread dans la sidebar pour explorer
              l'état de conversation.
            </div>
          </Card>
        </div>
      ) : (
        <div className="space-y-5">
          {/* MemoryFacts — mémoire cross-thread par catégories */}
          <LongTermMemoryCard
            overview={overview}
            loading={loading}
            onRefresh={refresh}
            onSaveProfile={updateProfile}
            onAddFact={addFact}
            onEditFact={editFact}
            onRemoveFact={removeFact}
            hasUser={Boolean(currentUser)}
          />

          {/* Context Inspector V4 — routing · context · prompt */}
          <ContextInspectorCard
            userId={currentUser?.user_id ?? null}
            threadId={currentThread.thread_id}
          />

          {/* Identifiants + compteurs */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            {stats.map(({ label, value, mono, truncate }) => (
              <Card key={label} className="p-3.5">
                <div className="mb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-[#94a3b8]/70">
                  {label}
                </div>
                <div
                  className={`${
                    mono
                      ? 'font-mono text-[11px] text-[#6c63ff]'
                      : 'text-lg font-semibold text-[#f5f7fa]'
                  } ${truncate ? 'truncate' : ''}`}
                  title={value}
                >
                  {mono && value !== '—' ? value.slice(0, 14) + '…' : value}
                </div>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            {/* Timeline des checkpoints */}
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-[13px]">
                  <Clock size={13} className="text-[#6c63ff]" strokeWidth={1.8} />
                  Conversation timeline
                </CardTitle>
                <span className="font-mono text-[10px] text-[#94a3b8]/60">
                  {history.length} checkpoints
                </span>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="py-8 text-center font-mono text-[11px] text-[#94a3b8]">
                    chargement…
                  </div>
                ) : history.length === 0 ? (
                  <div className="py-8 text-center font-mono text-[11px] text-[#94a3b8]">
                    Aucun checkpoint — envoyez un message dans ce thread.
                  </div>
                ) : (
                  <div className="max-h-[460px] space-y-0 overflow-y-auto pr-1">
                    {history.map((cp, i) => (
                      <motion.div
                        key={cp.checkpoint_id ?? i}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: Math.min(i * 0.025, 0.4), duration: 0.18 }}
                        className="relative flex gap-3 py-1.5"
                      >
                        {i < history.length - 1 && (
                          <div className="absolute left-[5px] top-6 h-full w-px bg-[#26323d]" />
                        )}
                        {/* Losange = checkpoint */}
                        <div
                          className={`relative mt-1 h-[10px] w-[10px] shrink-0 rotate-45 border ${
                            cp.summary.includes('Tool')
                              ? 'border-[#f59e0b] bg-[#f59e0b]/25'
                              : cp.summary.startsWith('User')
                                ? 'border-[#6c63ff] bg-[#6c63ff]/25'
                                : 'border-[#22c55e] bg-[#22c55e]/25'
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline gap-2">
                            <span className="font-mono text-[10px] font-semibold text-[#94a3b8]">
                              #{i + 1}
                            </span>
                            <span className="font-mono text-[10px] text-[#94a3b8]/50">
                              {cp.created_at?.split('T')[1]?.slice(0, 8) ?? ''}
                            </span>
                            <span className="font-mono text-[9px] text-[#94a3b8]/40">
                              {cp.message_count} msg
                            </span>
                          </div>
                          <div className="truncate text-xs text-[#f5f7fa]/90">
                            {cp.summary}
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* State courant */}
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-[13px]">
                  <Braces size={13} className="text-[#6c63ff]" strokeWidth={1.8} />
                  Current state
                </CardTitle>
                <button
                  onClick={() => setShowRaw(!showRaw)}
                  className={`rounded-md px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                    showRaw
                      ? 'bg-[#6c63ff] text-white'
                      : 'bg-[#18212b] text-[#94a3b8] hover:text-[#f5f7fa]'
                  }`}
                >
                  raw
                </button>
              </CardHeader>
              <CardContent>
                <AnimatePresence mode="wait">
                  {showRaw ? (
                    <motion.pre
                      key="raw"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="max-h-[460px] overflow-auto rounded-lg bg-[#0b0f14] p-3 font-mono text-[10.5px] leading-relaxed text-[#94a3b8]"
                    >
                      {JSON.stringify(state, null, 2)}
                    </motion.pre>
                  ) : (
                    <motion.div
                      key="readable"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="max-h-[460px] space-y-2 overflow-y-auto"
                    >
                      {state && state.messages.length > 0 ? (
                        state.messages.map((msg, i) => (
                          <div
                            key={i}
                            className="rounded-lg border border-[#26323d] bg-[#18212b] p-2.5"
                          >
                            <div className="mb-1.5 flex items-center gap-2">
                              <span
                                className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${
                                  msg.type === 'HumanMessage'
                                    ? 'bg-[#6c63ff]/15 text-[#6c63ff]'
                                    : msg.type === 'AIMessage'
                                      ? 'bg-[#22c55e]/15 text-[#22c55e]'
                                      : 'bg-[#f59e0b]/15 text-[#f59e0b]'
                                }`}
                              >
                                {msg.type === 'HumanMessage'
                                  ? 'user'
                                  : msg.type === 'AIMessage'
                                    ? 'assistant'
                                    : 'tool'}
                              </span>
                              {msg.tool_calls?.map((tc, j) => (
                                <span
                                  key={j}
                                  className="font-mono text-[10px] text-[#f59e0b]"
                                >
                                  {tc.name}()
                                </span>
                              ))}
                            </div>
                            <div className="line-clamp-3 text-xs leading-relaxed text-[#f5f7fa]/85">
                              {msg.content}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="py-8 text-center font-mono text-[11px] text-[#94a3b8]">
                          State vide pour ce thread.
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
