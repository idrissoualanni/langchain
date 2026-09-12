// LearningProfileCard V6 — progression pédagogique de l'étudiant
// Source de vérité : SqliteStore namespace ("users", "learning",
// user_id) — cross-thread, indépendant de la conversation.
// Deux modes : progression lisible (§35) et Raw Learning Profile
// (§36 — inspecteur dev : JSON réellement stocké).
import { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  Check,
  Code2,
  GraduationCap,
  RefreshCw,
} from 'lucide-react';
import {
  getLearningProfile,
  getLearningTopics,
} from '../../api/learning';
import type {
  LearningProfileData,
  TopicLearningData,
} from '../../types/learning';
import { Card } from '../ui/Card';

interface LearningProfileCardProps {
  userId: string | null;
}

function MasteryBar({ mastery }: { mastery: number | null }) {
  // Barre §35 : ███░░ 43% — null = jamais évalué (barre vide)
  const pct = mastery === null ? 0 : Math.round(mastery * 100);
  const filled = Math.round(pct / 12.5); // 8 blocs
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[11px] tracking-tighter text-[#f5f7fa]/90">
        {'█'.repeat(filled)}
        <span className="text-[#26323d]">
          {'░'.repeat(8 - filled)}
        </span>
      </span>
      <span className="font-mono text-[11px] font-semibold text-[#6c63ff]">
        {mastery === null ? '—' : `${pct}%`}
      </span>
    </div>
  );
}

function TopicRow({
  topicId,
  topic,
}: {
  topicId: string;
  topic: TopicLearningData;
}) {
  return (
    <div className="rounded-lg border border-[#26323d] bg-[#18212b] p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] font-semibold text-[#f5f7fa]">
          {topicId}
        </span>
        <MasteryBar mastery={topic.mastery} />
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[9.5px] text-[#94a3b8]">
        <span>attempts: {topic.attempts}</span>
        {topic.confidence !== null && (
          <span>
            confiance: {Math.round(topic.confidence * 100)}%
          </span>
        )}
        {topic.last_assessed_at && (
          <span>
            évalué le {topic.last_assessed_at.split('T')[0]}
          </span>
        )}
      </div>

      {topic.strengths.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {topic.strengths.slice(0, 3).map((s, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 text-[10.5px] text-[#22c55e]/90"
            >
              <Check size={10} strokeWidth={2.5} />
              {s}
            </div>
          ))}
        </div>
      )}
      {topic.weak_points.length > 0 && (
        <div className="mt-1 space-y-0.5">
          {topic.weak_points.slice(0, 3).map((w, i) => (
            <div
              key={i}
              className="flex items-center gap-1.5 text-[10.5px] text-[#f59e0b]/90"
            >
              <span className="font-bold">⚠</span>
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function LearningProfileCard({ userId }: LearningProfileCardProps) {
  const [profile, setProfile] = useState<LearningProfileData | null>(
    null
  );
  const [topics, setTopics] = useState<Record<
    string,
    { mastery: number | null; topics: Record<string, TopicLearningData> }
  > | null>(null);
  const [loading, setLoading] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const refresh = useCallback(async () => {
    if (!userId) {
      setProfile(null);
      setTopics(null);
      return;
    }
    setLoading(true);
    try {
      const [p, t] = await Promise.all([
        getLearningProfile(userId),
        getLearningTopics(userId),
      ]);
      setProfile(p);
      setTopics(t.subjects ?? {});
    } catch {
      setProfile(null);
      setTopics(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!userId) {
    return (
      <Card className="p-10 text-center">
        <GraduationCap
          size={32}
          className="mx-auto mb-3 text-[#94a3b8]/30"
        />
        <div className="text-sm text-[#94a3b8]">
          Sélectionnez un utilisateur pour voir sa progression
          d'apprentissage.
        </div>
      </Card>
    );
  }

  const subjectIds = Object.keys(topics ?? {});

  return (
    <Card>
      <div className="flex flex-row items-center justify-between border-b border-[#26323d] px-4 py-3">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-[#f5f7fa]">
          <GraduationCap
            size={14}
            className="text-[#6c63ff]"
            strokeWidth={1.8}
          />
          Learning Profile
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowRaw(!showRaw)}
            className={`rounded-md px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors ${
              showRaw
                ? 'bg-[#6c63ff] text-white'
                : 'bg-[#18212b] text-[#94a3b8] hover:text-[#f5f7fa]'
            }`}
            title="Raw Learning Profile (§36)"
          >
            <Code2 size={11} className="inline" /> raw
          </button>
          <button
            onClick={() => void refresh()}
            className="rounded-md bg-[#18212b] px-2 py-1 text-[#94a3b8] transition-colors hover:text-[#f5f7fa]"
            title="Rafraîchir"
          >
            <RefreshCw
              size={11}
              className={loading ? 'animate-spin' : ''}
            />
          </button>
        </div>
      </div>

      <div className="p-4">
        <AnimatePresence mode="wait">
          {showRaw ? (
            <motion.pre
              key="raw"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-[#0b0f14] p-3 font-mono text-[10.5px] leading-relaxed text-[#94a3b8]"
            >
              {JSON.stringify(profile, null, 2)}
            </motion.pre>
          ) : loading ? (
            <div className="py-8 text-center font-mono text-[11px] text-[#94a3b8]">
              chargement…
            </div>
          ) : profile === null || profile.status === 'not_started' ? (
            <div className="py-8 text-center font-mono text-[11px] text-[#94a3b8]">
              Aucun profil d'apprentissage — l'étudiant n'a encore
              jamais été évalué (cas normal, pas une erreur).
            </div>
          ) : subjectIds.length === 0 ? (
            <div className="py-8 text-center font-mono text-[11px] text-[#94a3b8]">
              Profil présent mais aucune progression enregistrée.
            </div>
          ) : (
            <motion.div
              key="progress"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="max-h-[420px] space-y-4 overflow-y-auto pr-1"
            >
              {subjectIds.map((sid) => {
                const s = topics![sid];
                const topicIds = Object.keys(s.topics);
                return (
                  <div key={sid}>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[12px] font-semibold uppercase tracking-wide text-[#f5f7fa]">
                        {sid}
                      </span>
                      <MasteryBar mastery={s.mastery} />
                    </div>
                    <div className="space-y-2">
                      {topicIds.map((tid) => (
                        <TopicRow
                          key={tid}
                          topicId={tid}
                          topic={s.topics[tid]}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}

              {profile.goals.length > 0 && (
                <div className="border-t border-[#26323d] pt-3">
                  <div className="mb-1.5 flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-[#94a3b8]">
                    <Activity size={11} /> Objectifs
                  </div>
                  {profile.goals.map((g) => (
                    <div
                      key={g.id}
                      className="flex items-center gap-2 py-0.5 text-[11px]"
                    >
                      <span
                        className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${
                          g.status === 'active'
                            ? 'bg-[#6c63ff]/15 text-[#6c63ff]'
                            : g.status === 'completed'
                              ? 'bg-[#22c55e]/15 text-[#22c55e]'
                              : 'bg-[#94a3b8]/15 text-[#94a3b8]'
                        }`}
                      >
                        {g.status}
                      </span>
                      <span className="text-[#f5f7fa]/85">
                        {g.description}
                      </span>
                      <span className="font-mono text-[9px] text-[#94a3b8]/60">
                        {g.subject}/{g.topic ?? '—'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Card>
  );
}
