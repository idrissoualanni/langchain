// MemoryPage â€” mÃ©moire LangGraph : profil longue durÃ©e, stats, checkpoints, state
// La sÃ©lection user/thread se fait dans la sidebar ; cette page
// affiche le contexte actif en lecture seule.
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity as ActivityIcon,
  Braces,
  Clock,
  Database,
  Terminal,
} from 'lucide-react';
import { useSelection } from '../hooks/useSelection';
import { useCurrentUser } from '../hooks/useCurrentUser';
import { useMemory } from '../hooks/useMemory';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { LongTermMemoryCard } from '../components/memory/LongTermMemoryCard';
import { ContextInspectorCard } from '../components/memory/ContextInspectorCard';
import { LearningProfileCard } from '../components/memory/LearningProfileCard';
import { ActivityFeed } from '../components/chat/ActivityFeed';
import { CodeEditor } from '../components/chat/CodeEditor';
import { CodeAnalysisPanel } from '../components/chat/CodeAnalysisPanel';

export function MemoryPage() {
  const { currentThread } = useSelection();
  // Mission Identité : user = SESSION ( Clerk/dev )
  const { internal: currentUser, signedIn } = useCurrentUser();
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
    signedIn ? currentUser?.user_id ?? null : null
  );

  const [showRaw, setShowRaw] = useState(false);

  const stats = [
    {
      label: 'user',
      value: state?.user_id ?? 'â€”',
      mono: true,
      truncate: true,
    },
    {
      label: 'thread',
      value: state?.thread_id ?? currentThread?.thread_id ?? 'â€”',
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
      {/* En-tête — humain (§12) : ce que l'agent sait, pourquoi c'est utile */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-foreground">
            <Database size={16} className="text-live" strokeWidth={1.8} />
            Mémoire
          </h1>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
            Ce que l’agent sait de vous, ce qu’il a mémorisé et comment cela personnalise vos apprentissages.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2 font-mono text-[11px]">
          {currentUser ? (
            <span className="max-w-[160px] truncate rounded-md bg-muted px-2 py-1 text-foreground/80">
              {currentUser.name}
            </span>
          ) : (
            <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground/60">
              no user
            </span>
          )}
          <span className="text-muted-foreground/40">/</span>
          {currentThread ? (
            <span
              className="max-w-[200px] truncate rounded-md bg-muted px-2 py-1 text-foreground/80"
              title={currentThread.thread_id}
            >
              {currentThread.name}
            </span>
          ) : (
            <span className="rounded-md bg-muted px-2 py-1 text-muted-foreground/60">
              no thread
            </span>
          )}
        </div>
      </div>

      {!currentThread ? (
        <div className="space-y-5">
          {/* MemoryFacts â€” visible mÃªme sans thread (user-only) */}
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
          {/* Context Inspector V4 â€” visible dÃ¨s qu'un user existe */}
          <ContextInspectorCard
            userId={currentUser?.user_id ?? null}
            threadId={null}
          />
          {/* Activity Feed V5.2 â€” fil d'activitÃ© du thread (Ã©tat vide
              sans thread : l'activitÃ© est thread-scoped Â§50) */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <ActivityIcon size={13} className="text-live" strokeWidth={1.8} />
                Activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ActivityFeed
                userId={currentUser?.user_id ?? null}
                threadId={null}
              />
            </CardContent>
          </Card>
          {/* Learning Profile V6 â€” progression cross-thread (Â§35/Â§36) */}
          <LearningProfileCard userId={currentUser?.user_id ?? null} />
          <Card className="p-10 text-center">
            <Database size={32} className="mx-auto mb-3 text-muted-foreground/30" />
            <div className="text-sm text-muted-foreground">
              SÃ©lectionnez un thread dans la sidebar pour explorer
              l'Ã©tat de conversation.
            </div>
          </Card>
        </div>
      ) : (
        <div className="space-y-5">
          {/* MemoryFacts â€” mÃ©moire cross-thread par catÃ©gories */}
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

          {/* Context Inspector V4 â€” routing Â· context Â· prompt */}
          <ContextInspectorCard
            userId={currentUser?.user_id ?? null}
            threadId={currentThread.thread_id}
          />

          {/* Activity Feed V5.2 â€” Ã©vÃ©nements pÃ©dagogiques du thread (Â§42) */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <ActivityIcon size={13} className="text-live" strokeWidth={1.8} />
                Activity
              </CardTitle>
              <span className="font-mono text-[10px] text-muted-foreground/60">
                thread-local Â· 30s auto-refresh
              </span>
            </CardHeader>
            <CardContent>
              <ActivityFeed
                userId={currentUser?.user_id ?? null}
                threadId={currentThread.thread_id}
              />
            </CardContent>
          </Card>

          {/* Learning Profile V6 â€” progression cross-thread (Â§35/Â§36) */}
          <LearningProfileCard userId={currentUser?.user_id ?? null} />

          {/* Code Practice V5.2 â€” Ã©diteur + analyse (Â§24-Â§31) */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-[13px]">
                <Terminal size={13} className="text-live" strokeWidth={1.8} />
                Code Practice
              </CardTitle>
              <span className="font-mono text-[10px] text-muted-foreground/60">
                sandbox isolÃ©e Â· python
              </span>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <CodeEditor
                  userId={currentUser?.user_id ?? null}
                  threadId={currentThread.thread_id}
                />
                <CodeAnalysisPanel analysis={null} />
              </div>
            </CardContent>
          </Card>

          {/* Métriques humaines — IDs cachés (§12) */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {stats.slice(2).map(({ label, value }) => (
              <Card key={label} className="p-3.5">
                <div className="mb-1 font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground/70">
                  {label}
                </div>
                <div className="text-lg font-semibold text-foreground">{value}</div>
              </Card>
            ))}
          </div>
          <details className="rounded-lg border border-border bg-muted/20 px-4 py-2">
            <summary className="cursor-pointer font-mono text-[11px] text-muted-foreground hover:text-foreground">
              Détails techniques (IDs, checkpoints)
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11px]">
              <span className="text-muted-foreground">user</span>
              <span className="truncate text-live">{state?.user_id ?? '—'}</span>
              <span className="text-muted-foreground">thread</span>
              <span className="truncate text-live">{currentThread?.thread_id ?? '—'}</span>
            </div>
          </details>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            {/* Timeline des checkpoints */}
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-[13px]">
                  <Clock size={13} className="text-live" strokeWidth={1.8} />
                  Conversation timeline
                </CardTitle>
                <span className="font-mono text-[10px] text-muted-foreground/60">
                  {history.length} checkpoints
                </span>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                    chargementâ€¦
                  </div>
                ) : history.length === 0 ? (
                  <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
                    Aucun checkpoint â€” envoyez un message dans ce thread.
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
                          <div className="absolute left-[5px] top-6 h-full w-px bg-border" />
                        )}
                        {/* Losange = checkpoint â€” couleur par champ
                            structurÃ© `kind` (V6.8 audit Â§62 : plus
                            de parsing du texte summary) */}
                        <div
                          className={`relative mt-1 h-[10px] w-[10px] shrink-0 rotate-45 border ${
                            cp.kind === 'tool_call' || cp.kind === 'tool_result'
                              ? 'border-warning bg-warning/25'
                              : cp.kind === 'user_message'
                                ? 'border-live bg-live/25'
                                : 'border-success bg-success/25'
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline gap-2">
                            <span className="font-mono text-[10px] font-semibold text-muted-foreground">
                              #{i + 1}
                            </span>
                            <span className="font-mono text-[10px] text-muted-foreground/50">
                              {cp.created_at?.split('T')[1]?.slice(0, 8) ?? ''}
                            </span>
                            <span className="font-mono text-[9px] text-muted-foreground/40">
                              {cp.message_count} msg
                            </span>
                          </div>
                          <div className="truncate text-xs text-foreground/90">
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
                  <Braces size={13} className="text-live" strokeWidth={1.8} />
                  Current state
                </CardTitle>
                <button
                  onClick={() => setShowRaw(!showRaw)}
                  className={`rounded-md px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                    showRaw
                      ? 'bg-live text-white'
                      : 'bg-muted text-muted-foreground hover:text-foreground'
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
                      className="max-h-[460px] overflow-auto rounded-lg bg-background p-3 font-mono text-[10.5px] leading-relaxed text-muted-foreground"
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
                            className="rounded-lg border border-border bg-muted p-2.5"
                          >
                            <div className="mb-1.5 flex items-center gap-2">
                              <span
                                className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide ${
                                  msg.type === 'HumanMessage'
                                    ? 'bg-live/15 text-live'
                                    : msg.type === 'AIMessage'
                                      ? 'bg-success/15 text-success'
                                      : 'bg-warning/15 text-warning'
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
                                  className="font-mono text-[10px] text-warning"
                                >
                                  {tc.name}()
                                </span>
                              ))}
                            </div>
                            <div className="line-clamp-3 text-xs leading-relaxed text-foreground/85">
                              {msg.content}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="py-8 text-center font-mono text-[11px] text-muted-foreground">
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
