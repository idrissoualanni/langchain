// API Memory — state + history + profil + MemoryFacts v3
import type {
  Checkpoint,
  MemoryFact,
  MemoryOverview,
  ThreadState,
  UserProfile,
} from '../types/agent';
import { apiFetch } from './base';

export async function getThreadState(
  threadId: string,
  userId?: string
): Promise<ThreadState> {
  const qs = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
  return apiFetch<ThreadState>(`/api/threads/${threadId}/state${qs}`);
}

export async function getThreadHistory(
  threadId: string,
  userId?: string
): Promise<Checkpoint[]> {
  const qs = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
  return apiFetch<Checkpoint[]>(
    `/api/threads/${threadId}/history${qs}`
  );
}

// ---- Mémoire longue durée (profil user, cross-thread) ----

export async function getUserProfile(
  userId: string
): Promise<UserProfile> {
  return apiFetch<UserProfile>(`/api/users/${userId}/profile`);
}

export async function updateUserProfile(
  userId: string,
  fields: { name?: string; description?: string }
): Promise<UserProfile> {
  return apiFetch<UserProfile>(`/api/users/${userId}/profile`, {
    method: 'PUT',
    body: JSON.stringify(fields),
  });
}

// ---- MemoryFacts v3 (faits individuels par catégorie) ----

export async function getMemoryOverview(
  userId: string
): Promise<MemoryOverview> {
  return apiFetch<MemoryOverview>(`/api/users/${userId}/memory`);
}

export async function createMemoryFact(
  userId: string,
  fact: { category: string; content: string; confidence?: number }
): Promise<MemoryFact> {
  return apiFetch<MemoryFact>(`/api/users/${userId}/memory/facts`, {
    method: 'POST',
    body: JSON.stringify(fact),
  });
}

export async function updateMemoryFact(
  userId: string,
  factId: string,
  fields: { content?: string; category?: string }
): Promise<MemoryFact> {
  return apiFetch<MemoryFact>(
    `/api/users/${userId}/memory/facts/${factId}`,
    {
      method: 'PUT',
      body: JSON.stringify(fields),
    }
  );
}

export async function deleteMemoryFact(
  userId: string,
  factId: string
): Promise<{ deleted: string }> {
  return apiFetch<{ deleted: string }>(
    `/api/users/${userId}/memory/facts/${factId}`,
    {
      method: 'DELETE',
    }
  );
}
