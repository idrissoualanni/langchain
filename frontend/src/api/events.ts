// SSE — bus d'événements agent temps réel
import type { AgentEvent } from '../types/agent';

/**
 * Connexion au flux SSE /api/events.
 * Retourne une fonction de déconnexion.
 * Reconnexion automatique native via EventSource.
 */
export function connectAgentEvents(
  onEvent: (event: AgentEvent) => void
): () => void {
  const source = new EventSource('/api/events');

  source.addEventListener('agent-event', (e) => {
    try {
      onEvent(JSON.parse((e as MessageEvent).data));
    } catch {
      /* ignore */
    }
  });

  source.onerror = () => {
    // EventSource reconnecte automatiquement
  };

  return () => source.close();
}
