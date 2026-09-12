// Types Activity V5.2 — activité pédagogique thread-local + pratique du code
//
// Contrat backend (app/api/schemas.py + app/agent/activity_state.py) :
//   - ActivitySummary NE CONTIENT JAMAIS les réponses attendues
//     (le backend les exclut dans summarize_activity) ;
//   - activity_log = événements réels ACTIVITY_*/QUIZ_*/CODE_* du
//     state LangGraph, jamais fabriqués côté frontend ;
//   - CodeRunResult = résultat de la sandbox isolée (§24-§27).

/** Statuts d'activité émis par le backend (app/agent/activity_state.py). */
export type ActivityStatus =
  | 'idle'
  | 'waiting_for_answer'
  | 'evaluating'
  | 'giving_hint'
  | 'waiting_for_retry'
  | 'checking_understanding'
  | 'completed'
  | 'abandoned'
  | string; // statuts futurs non cassants

/** Types d'activité pédagogique (exercise | quiz | understanding_check). */
export type ActivityType =
  | 'exercise'
  | 'quiz'
  | 'understanding_check'
  | 'code_practice'
  | string;

/** Type de réponse attendue par l'activité en cours (§23). */
export type ExpectedResponseType =
  | 'text'
  | 'code'
  | 'multiple_choice'
  | 'short_answer'
  | 'true_false'
  | string;

/** Vue compacte de l'activité en cours — sans fuiter les réponses attendues.
 *
 * Champs du contrat Pydantic ActivitySummary (app/api/schemas.py) ;
 * les champs du brief V5.2 absents du backend actuel sont optionnels
 * (défensif : le composant saute ce qu'il n'a pas).
 */
export interface ActivitySummary {
  activity_id: string;
  activity_type: ActivityType | null;
  subject: string | null;
  topic: string | null;
  status: ActivityStatus;
  hint_level: number;
  attempts: number;
  awaiting_answer: boolean;
  expected_response_type: ExpectedResponseType;
  question_index: number;
  total_questions: number;
  current_index: number;
  score: number | null;
  // Champs présents dans le brief §42 — absents du backend actuel,
  // tolérés s'ils apparaissent (affichage conditionnel).
  question_preview?: string;
  last_evaluation?: unknown;
  understanding?: unknown;
  quiz?: {
    current_index: number;
    score: number;
    total_questions: number;
  } | null;
}

/** Une entrée du journal d'activité thread-local (§42). */
export interface ActivityLogEntry {
  timestamp: string;
  event: string; // ACTIVITY_* | QUIZ_* | CODE_*
  status: string;
  detail: string;
  hint_level: number;
  activity_type: string;
}

/** Réponse GET /api/threads/{id}/activity?user_id=… */
export interface ThreadActivityResponse {
  thread_id: string;
  user_id: string;
  activity: ActivitySummary | null;
  activity_log: ActivityLogEntry[];
  interaction_count: number;
}

/** Résultat d'exécution sandbox (POST /api/threads/{id}/run-code). */
export interface CodeRunResult {
  status: 'success' | 'error' | 'timeout' | string;
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
}
