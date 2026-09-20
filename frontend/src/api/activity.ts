// API Activity V5.2 — activité pédagogique du thread + exécution
// directe de code étudiant dans la sandbox backend (§24-§26).
//
// Isolation (§51) : le user_id est systématiquement transmis — le
// backend rejette 403 si le thread n'appartient pas à cet utilisateur.
import type {
  CodeRunResult,
  ThreadActivityResponse,
} from '../types/activity';
import { apiFetch } from './base';

/** État de l'activité pédagogique en cours dans CE thread (§42). */
export async function getThreadActivity(
  threadId: string,
  userId: string
): Promise<ThreadActivityResponse> {
  return apiFetch<ThreadActivityResponse>(
    `/api/threads/${threadId}/activity?user_id=${encodeURIComponent(userId)}`
  );
}

/** Exécute le code de l'éditeur dans la sandbox isolée backend.
 *
 * Retourne stdout/stderr/exit_code/duration réels. Le backend peut
 * rejeter 400 (code interdit par le scan statique de sécurité) ou
 * 403 (thread d'un autre utilisateur) — l'ApiError remonte son
 * detail au composant appelant.
 */
export async function runCode(
  threadId: string,
  userId: string,
  code: string
): Promise<CodeRunResult> {
  return apiFetch<CodeRunResult>(
    `/api/threads/${threadId}/run-code`,
    {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        language: 'python',
        code,
      }),
    }
  );
}
