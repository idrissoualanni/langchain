// API Threads
import type { Thread } from '../types/agent';
import { apiFetch } from './base';

export async function listThreads(userId: string): Promise<Thread[]> {
  return apiFetch<Thread[]>(`/api/users/${userId}/threads`);
}

export async function getThread(threadId: string): Promise<Thread> {
  return apiFetch<Thread>(`/api/threads/${threadId}`);
}

export async function createThread(
  userId: string,
  name: string
): Promise<Thread> {
  return apiFetch<Thread>(`/api/users/${userId}/threads`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}
