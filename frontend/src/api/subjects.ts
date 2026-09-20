// API Subjects — registry + context preview (V4)
import type { ContextPreview, SubjectInfo } from '../types/agent';
import { apiFetch } from './base';

export async function listSubjects(): Promise<SubjectInfo[]> {
  return apiFetch<SubjectInfo[]>('/api/subjects');
}

export async function getSubject(id: string): Promise<SubjectInfo> {
  return apiFetch<SubjectInfo>(`/api/subjects/${id}`);
}

export interface SubjectTopic {
  id: string;
  subject_id: string;
  name: string;
}

export async function getSubjectTopics(
  id: string
): Promise<SubjectTopic[]> {
  return apiFetch<SubjectTopic[]>(`/api/subjects/${id}/topics`);
}

export async function previewContext(payload: {
  user_id: string;
  thread_id?: string;
  query: string;
  subject?: string;
}): Promise<ContextPreview> {
  return apiFetch<ContextPreview>(
    '/api/subjects/preview/context',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}
