// API Learning V6 — Learning Profile (lecture seule : les tools
// LLM restent la voie d'écriture)
import type {
  LearningGoalData,
  LearningObservationData,
  LearningProfileData,
  LearningTopicsResponse,
  TopicLearningData,
} from '../types/learning';
import { apiFetch } from './base';

export async function getLearningProfile(
  userId: string
): Promise<LearningProfileData> {
  return apiFetch<LearningProfileData>(
    `/api/learning/${userId}/profile`
  );
}

export async function getLearningTopics(
  userId: string
): Promise<LearningTopicsResponse> {
  return apiFetch<LearningTopicsResponse>(
    `/api/learning/${userId}/topics`
  );
}

export async function getLearningTopic(
  userId: string,
  subject: string,
  topic: string
): Promise<TopicLearningData & { status: string }> {
  return apiFetch(`/api/learning/${userId}/${subject}/${topic}`);
}

export async function getLearningObservations(
  userId: string,
  opts: { limit?: number; subject?: string; topic?: string } = {}
): Promise<LearningObservationData[]> {
  const params = new URLSearchParams();
  params.set('limit', String(opts.limit ?? 50));
  if (opts.subject) params.set('subject', opts.subject);
  if (opts.topic) params.set('topic', opts.topic);
  return apiFetch(
    `/api/learning/${userId}/observations?${params.toString()}`
  );
}

export async function getLearningGoals(
  userId: string
): Promise<LearningGoalData[]> {
  return apiFetch(`/api/learning/${userId}/goals`);
}
