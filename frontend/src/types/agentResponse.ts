// ---- V6.7 : AgentResponse (contrat public backend) ----
// ADDENDUM : 5 statuts publics EXACTEMENT — success interdit.

export type AgentResponseStatus =
  | 'completed'
  | 'waiting_for_user'
  | 'running'
  | 'error'
  | 'cancelled';

export type AgentResponseType =
  | 'text'
  | 'exercise'
  | 'quiz'
  | 'evaluation'
  | 'hint'
  | 'code'
  | 'search'
  | 'clarification'
  | 'error';

export interface AgentResponseAction {
  type: string;
  options?: string[];
  [key: string]: unknown;
}

export interface AgentResponse {
  version: number;
  type: AgentResponseType;
  status: AgentResponseStatus;
  message: string;
  data: Record<string, unknown>;
  actions: AgentResponseAction[];
}

// ---- data typée par response.type (§20-§23) ----

export interface ExerciseData {
  activity_id: string;
  activity_status: string;
  subject?: string | null;
  topic?: string | null;
  question?: string;
  difficulty?: string;
  language?: string;
}

export interface QuizData extends ExerciseData {
  question_index: number;
  total_questions: number;
}

export interface CodeData extends ExerciseData {
  language: string;
  starter_code: string;
}

export interface EvaluationData extends ExerciseData {
  score?: number;
  verdict?: string;
  strengths?: string[];
  weak_points?: string[];
  next_action?: string;
}

export interface HintData extends ExerciseData {
  hint_level: number;
}

export interface SearchData {
  results: {
    title: string;
    source: string;
    url: string | null;
    snippet: string;
  }[];
  result_count: number;
}

export interface ClarificationData {
  candidates: string[];
}
