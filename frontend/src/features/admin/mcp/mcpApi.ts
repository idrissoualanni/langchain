// API layer — Inspecteur MCP (admin).
//
// Le navigateur ne parle JAMAIS le protocole MCP : il ne sait pas
// adresser un pipe de processus, et exposer du stdio en HTTP
// obligerait à transporter l'identité utilisateur par header (faille
// §41). On passe donc par REST au backend, qui possède le pool de
// sessions stdio et connaît l'utilisateur connecté côté serveur.
import { apiRequest } from '@/api/request';

export interface McpServer {
  name: string;
  transport: string;
  enabled: boolean;
  capabilities: string[];
  allowed_workflows: string[];
  timeout_s: number;
  rate_limit: number | null;
  description: string;
}

export interface McpTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
}

export interface McpToolsResponse {
  server: string;
  tools: McpTool[];
  duration_ms: number;
}

export interface McpContentBlock {
  type: string;
  text?: string;
  repr?: string;
}

export interface McpInvokeResult {
  server: string;
  tool: string;
  ok: boolean;
  content: McpContentBlock[];
  structured_content: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
}

const BASE = '/api/admin/mcp';

/** Extrait le `detail` FastAPI, sinon un message générique lisible. */
async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === 'string'
      ? body.detail
      : JSON.stringify(body.detail ?? body);
  } catch {
    return res.statusText || `Erreur ${res.status}`;
  }
}

export async function fetchMcpServers(): Promise<McpServer[]> {
  const res = await apiRequest(`${BASE}/servers`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json() as Promise<McpServer[]>;
}

export async function fetchMcpTools(name: string): Promise<McpToolsResponse> {
  const res = await apiRequest(`${BASE}/servers/${encodeURIComponent(name)}/tools`);
  if (!res.ok) throw new Error(await readError(res));
  return res.json() as Promise<McpToolsResponse>;
}

export async function invokeMcpTool(
  name: string,
  tool: string,
  args: Record<string, unknown>
): Promise<McpInvokeResult> {
  const res = await apiRequest(
    `${BASE}/servers/${encodeURIComponent(name)}/tools/${encodeURIComponent(tool)}/invoke`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arguments: args }),
    }
  );
  if (!res.ok) throw new Error(await readError(res));
  return res.json() as Promise<McpInvokeResult>;
}
