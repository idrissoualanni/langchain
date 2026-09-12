// Types partagés — Agent Control Center
import type { LearningContextData } from './learning';

export type { LearningContextData };

export interface User {
  user_id: string;
  name: string;
  created_at: string;
}

export interface Thread {
  thread_id: string;
  user_id: string;
  name: string;
  created_at: string;
}

export type MessageRole = 'user' | 'assistant' | 'tool';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  toolName?: string;
}

export type ToolStatus = 'idle' | 'running' | 'success' | 'error';

export interface ToolExecution {
  id: string;
  toolName: string;
  status: ToolStatus;
  input?: string;
  output?: string;
  error?: string;
  durationMs?: number;
  timestamp: string;
}

export interface AgentEvent {
  timestamp: string;
  level: string;
  event: string;
  user_id?: string;
  thread_id?: string;
  tool_name?: string;
  message?: string;
  input?: string;
  output?: string;
  error?: string;
  duration_ms?: number;
  checkpoint_id?: string;
  response?: string;
  interaction_count?: number;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  event: string;
  user_id?: string;
  thread_id?: string;
  tool_name?: string;
  message?: string;
}

export interface HealthInfo {
  status: string;
  ollama: boolean;
  langgraph: boolean;
  sqlite: boolean;
  model: string;
}

export interface StateMessage {
  type: string;
  content: string;
  tool_calls: { name: string; args: Record<string, unknown> }[] | null;
}

export interface ThreadState {
  user_id: string;
  thread_id: string;
  interaction_count: number;
  message_count: number;
  messages: StateMessage[];
}

export interface Checkpoint {
  checkpoint_id: string | null;
  created_at: string;
  message_count: number;
  interaction_count: number;
  summary: string;
}

export interface ChatResponse {
  response: string;
  user_id: string;
  thread_id: string;
  interaction_count: number;
}

// ---- Mémoire longue durée ----

export interface UserProfile {
  user_id: string;
  name: string | null;
  description: string | null;
  exists: boolean;
}

// ---- MemoryFacts v3 ----

export const MEMORY_CATEGORIES = [
  'identity',
  'background',
  'personality',
  'preference',
  'interest',
] as const;

export type MemoryCategory =
  typeof MEMORY_CATEGORIES[number];

export const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  identity: 'Identity',
  background: 'Background',
  personality: 'Personality',
  preference: 'Preferences',
  interest: 'Interests',
};

export interface MemoryFact {
  id: string;
  category: MemoryCategory;
  content: string;
  source: string;
  confidence: number;
  created_at: string;
  updated_at: string;
}

export interface MemoryOverview {
  user_id: string;
  identity: { name: string | null; description: string | null };
  facts_by_category: Record<string, MemoryFact[]>;
  total_facts: number;
  categories: string[];
}

// ---- V4 — Subjects & Context Engineering ----

export interface SubjectInfo {
  id: string;
  name: string;
  domain: string;
  description: string;
  teaching_style: string[];
  pedagogical_guidelines: string[];
  capabilities: string[];
  topics: string[];
  knowledge_sources: string[];
  tools_common: string[];
  tools_specialized: string[];
}

export type RouterStatus =
  | 'supported'
  | 'ambiguous'
  | 'unsupported'
  | 'unknown'
  | 'multi_domain';

export interface RouterInfo {
  subject: string | null;
  topic: string | null;
  confidence: number;
  status: RouterStatus;
  candidates: string[];
  subjects: string[];
}

export interface KnowledgeItem {
  source: string;
  topic: string;
  content: string;
  relevance: number;
}

export interface KnowledgeContext {
  status: 'found' | 'insufficient' | 'unavailable';
  items: KnowledgeItem[];
  searched_sources: number;
}

// ---- V6.5 : Search unifié (§3 Search Contract) ----

export interface SearchResultItem {
  title: string;
  source: string;
  url: string | null;
  content: string;
  snippet: string | null;
  relevance: number;
  source_type: 'local_knowledge' | 'web' | 'user_document' | 'other';
  metadata: Record<string, unknown>;
}

export interface SearchWebResponse {
  status: 'found' | 'insufficient' | 'unavailable' | 'error';
  query: string;
  results: SearchResultItem[];
}

// ---- V5 : ToolsContext = ResolvedTools (resolve_tools §28/§39) ----

export interface ToolsContext {
  available: string[];
  declared: string[];
  unavailable: string[];
}

/** SubjectConfig telle qu'exposée par le builder (sans topics/tools_*) */
export interface SubjectContextInfo {
  id: string;
  name: string;
  domain: string;
  description: string;
  teaching_style: string[];
  pedagogical_guidelines: string[];
  capabilities: string[];
}

export interface ContextPreview {
  router: RouterInfo;
  subject: SubjectContextInfo | null;
  knowledge: KnowledgeContext;
  web?: SearchWebResponse; // V6.5 §29 — search inspector
  tools: ToolsContext;
  user: { text: string; facts_count: number };
  thread: {
    thread_id: string;
    message_count: number | null;
    text: string;
  };
  learning?: LearningContextData | null; // V6
  prompt_preview: string;
  stats: Record<string, number>;
}

// ---- V6 + V5.2 — Tools disponibles (24 avec activity/code) ----
export const TOOL_NAMES = [
  'additionner',
  'calculer_longueur_texte',
  'recherche_web',
  'get_user_profile',
  'update_user_profile',
  'get_user_memory',
  'save_user_memory',
  'update_user_memory',
  'delete_user_memory',
  'search_user_memory',
  // V4.1 — pédagogiques communs (implémentations réelles)
  'create_exercise',
  'evaluate_answer',
  'give_hint',
  // V6 — Learning Profile
  'get_learning_profile',
  'get_learning_topic',
  'record_learning_observation',
  'update_learning_goal',
  // V5.2 — activités pédagogiques interactives (quiz, compréhension)
  'create_quiz',
  'create_quiz_next',
  'assess_understanding',
  'propose_review',
  // V5.2 — pratique du code (sandbox isolée, §24-§30)
  'execute_code',
  'run_tests',
  'analyze_code',
] as const;
