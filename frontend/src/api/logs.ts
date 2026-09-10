// API Logs + Health
import type { HealthInfo, LogEntry } from '../types/agent';
import { apiFetch } from './base';

export async function getLogs(
  limit = 200,
  filters?: { level?: string; event?: string; threadId?: string }
): Promise<LogEntry[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters?.level) params.set('level', filters.level);
  if (filters?.event) params.set('event', filters.event);
  if (filters?.threadId) params.set('thread_id', filters.threadId);
  return apiFetch<LogEntry[]>(`/api/logs?${params}`);
}

export async function getHealth(): Promise<HealthInfo> {
  return apiFetch<HealthInfo>('/api/health');
}
