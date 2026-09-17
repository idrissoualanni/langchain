// Hook Learning — agrège les données backend réellement disponibles
// (profile, topics, observations, goals) en une vue unique pour les
// pages /learning. AUCUNE statistique inventée : tout est dérivé des
// valeurs renvoyées par l'API. En l'absence de données, on renvoie
// des listes vides (les pages affichent alors un état vide explicite).
import { useCallback, useEffect, useState } from 'react';
import {
  getLearningGoals,
  getLearningObservations,
  getLearningProfile,
  getLearningTopics,
} from '../api/learning';
import type {
  LearningGoalData,
  LearningObservationData,
  TopicLearningData,
} from '../types/learning';

export interface LearningTopicView {
  id: string;
  data: TopicLearningData;
}

export interface LearningSubjectView {
  id: string;
  mastery: number | null;
  topics: LearningTopicView[];
}

export interface LearningWeakPoint {
  subject: string;
  topic: string;
  points: string[];
  mastery: number | null;
  lastAssessedAt: string | null;
}

export interface LearningStrength {
  subject: string;
  topic: string;
  points: string[];
}

export interface LearningData {
  /** 'active' si le backend a un profil, sinon 'not_started'. */
  status: 'active' | 'not_started';
  subjects: LearningSubjectView[];
  goals: LearningGoalData[];
  observations: LearningObservationData[];
  weakPoints: LearningWeakPoint[];
  strengths: LearningStrength[];
  /** Moyenne des masteries de matières réellement évaluées (calculée). */
  globalMastery: number | null;
  assessedSubjectCount: number;
  subjectCount: number;
  topicCount: number;
  assessedTopicCount: number;
  lastActivityAt: string | null;
}

const EMPTY: LearningData = {
  status: 'not_started',
  subjects: [],
  goals: [],
  observations: [],
  weakPoints: [],
  strengths: [],
  globalMastery: null,
  assessedSubjectCount: 0,
  subjectCount: 0,
  topicCount: 0,
  assessedTopicCount: 0,
  lastActivityAt: null,
};

function derive(
  profileStatus: 'active' | 'not_started',
  subjects: Record<
    string,
    { mastery: number | null; topics: Record<string, TopicLearningData> }
  >,
  goals: LearningGoalData[],
  observations: LearningObservationData[]
): LearningData {
  const subjectViews: LearningSubjectView[] = Object.keys(subjects)
    .sort()
    .map((sid) => {
      const s = subjects[sid];
      return {
        id: sid,
        mastery: s.mastery ?? null,
        topics: Object.keys(s.topics ?? {})
          .sort()
          .map((tid) => ({ id: tid, data: s.topics[tid] })),
      };
    });

  const weakPoints: LearningWeakPoint[] = [];
  const strengths: LearningStrength[] = [];
  let topicCount = 0;
  let assessedTopicCount = 0;

  for (const s of subjectViews) {
    for (const t of s.topics) {
      topicCount += 1;
      if (t.data.mastery !== null || t.data.attempts > 0) {
        assessedTopicCount += 1;
      }
      if (t.data.weak_points?.length) {
        weakPoints.push({
          subject: s.id,
          topic: t.id,
          points: t.data.weak_points,
          mastery: t.data.mastery,
          lastAssessedAt: t.data.last_assessed_at,
        });
      }
      if (t.data.strengths?.length) {
        strengths.push({
          subject: s.id,
          topic: t.id,
          points: t.data.strengths,
        });
      }
    }
  }

  // Points faibles : mastery croissante (les plus faibles d'abord)
  weakPoints.sort(
    (a, b) => (a.mastery ?? -1) - (b.mastery ?? -1)
  );

  const assessed = subjectViews.filter((s) => s.mastery !== null);
  const globalMastery =
    assessed.length > 0
      ? assessed.reduce((sum, s) => sum + (s.mastery ?? 0), 0) /
        assessed.length
      : null;

  const sortedObservations = [...observations].sort(
    (a, b) =>
      new Date(b.created_at).getTime() -
      new Date(a.created_at).getTime()
  );

  return {
    status: profileStatus,
    subjects: subjectViews,
    goals,
    observations: sortedObservations,
    weakPoints,
    strengths,
    globalMastery,
    assessedSubjectCount: assessed.length,
    subjectCount: subjectViews.length,
    topicCount,
    assessedTopicCount,
    lastActivityAt: sortedObservations[0]?.created_at ?? null,
  };
}

export function useLearning(userId: string | null) {
  const [data, setData] = useState<LearningData>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!userId) {
      setData(EMPTY);
      return;
    }
    setLoading(true);
    setError(null);
    const [profileRes, topicsRes, goalsRes, obsRes] =
      await Promise.allSettled([
        getLearningProfile(userId),
        getLearningTopics(userId),
        getLearningGoals(userId),
        getLearningObservations(userId, { limit: 50 }),
      ]);

    const profile =
      profileRes.status === 'fulfilled' ? profileRes.value : null;
    const topics =
      topicsRes.status === 'fulfilled' ? topicsRes.value : null;
    const goals = goalsRes.status === 'fulfilled' ? goalsRes.value : [];
    const observations =
      obsRes.status === 'fulfilled' ? obsRes.value : [];

    // Le profil est la source du statut ; les topics portent la
    // progression détaillée. Les deux peuvent être vides.
    const subjects =
      topics?.subjects ?? profile?.subjects ?? {};
    const status: 'active' | 'not_started' =
      profile?.status ?? topics?.status ?? 'not_started';

    if (
      profileRes.status === 'rejected' &&
      topicsRes.status === 'rejected'
    ) {
      setError('Impossible de charger les données d’apprentissage.');
    }

    setData(
      derive(
        status,
        subjects,
        goals,
        observations as LearningObservationData[]
      )
    );
    setLoading(false);
  }, [userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}
