// API Learning V6 — Learning Profile (lecture seule : les tools
// LLM restent la voie d'écriture)
import type { LearningProfileData, TopicLearningData } from '../types/learning';
import { apiFetch } from './base';

export async function getLearningProfile(
  userId: string
): Promise<LearningProfileData> {
  return apiFetch<LearningProfileData>(
    `/api/learning/${userId}/profile`
  );
}

export async function getLearningTopics(userId: string): Promise<{
  status: string;
  subjects: Record<
    string,
    { mastery: number | null; topics: Record<string, TopicLearningData> }
  >;
}> {
  return apiFetch(`/api/learning/${userId}/topics`);
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
  limit = 50
): Promise<Array<Record<string, unknown>>> {
  return apiFetch(
    `/api/learning/${userId}/observations?limit=${limit}`
  );
}

export async function getLearningGoals(
  userId: string
): Promise<Array<Record<string, unknown>>> {
  return apiFetch(`/api/learning/${userId}/goals`);
}
