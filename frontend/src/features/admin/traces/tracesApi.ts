// API layer — tracing / debugging LangSmith (admin).
import { apiRequest } from '@/api/request';

export interface TraceRun {
  run_id: string;
  name?: string | null;
  project_name?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  status: string;
  workflow?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  tokens?: Record<string, number> | null;
  error_message?: string | null;
}

export interface TraceSpan {
  run_id: string;
  name: string;
  run_type: string;
  status?: string | null;
  latency_ms?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  error?: string | null;
  metadata: Record<string, unknown>;
  feedback?: Record<string, unknown> | null;
  child_runs: TraceSpan[];
}

export interface TraceError {
  run_id: string;
  timestamp: string;
  error_type: string;
  error_message: string;
  workflow?: string | null;
  node?: string | null;
}

export interface ModelUsage {
  model_name: string;
  provider?: string | null;
  total_calls: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost?: number | null;
  avg_latency_ms?: number | null;
}

const BASE = '/api/admin/observability';

async function getJson<T>(path: string): Promise<T> {
  const res = await apiRequest(path);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Requête échouée (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function fetchRuns(params: { limit?: number; status?: string } = {}): Promise<TraceRun[]> {
  const q = new URLSearchParams();
  q.set('limit', String(params.limit ?? 50));
  if (params.status && params.status !== 'all') q.set('status_filter', params.status);
  return getJson<TraceRun[]>(`${BASE}/runs?${q.toString()}`);
}

export function fetchRunDetail(runId: string): Promise<TraceSpan> {
  return getJson<TraceSpan>(`${BASE}/run/${encodeURIComponent(runId)}`);
}

export function fetchErrors(limit = 25): Promise<TraceError[]> {
  return getJson<TraceError[]>(`${BASE}/errors?limit=${limit}`);
}

export function fetchModelUsage(days = 7): Promise<ModelUsage[]> {
  return getJson<ModelUsage[]>(`${BASE}/models/usage?days=${days}`);
}

export function fetchObservabilitySummary(): Promise<Record<string, unknown>> {
  return getJson<Record<string, unknown>>(`${BASE}/summary`);
}