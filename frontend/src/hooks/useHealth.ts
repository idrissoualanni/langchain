// Hook Health — statuts Ollama / LangGraph / SQLite
//
// Polling CONDITIONNEL : l'indicateur de santé des services a quitté la
// sidebar (redondant avec le dashboard Admin → /admin). useHealth() n'est
// donc plus monté que par des consommateurs RÉELS ( sélecteur de modèle
// sur /assistant, pages Admin ). On ne poll /api/health toutes les 30 s
// que si l'onglet est VISIBLE et la page montée — sinon un onglet en
// arrière-plan continue de marteler l'API indéfiniment.
import { useCallback, useEffect, useState } from 'react';
import type { HealthInfo } from '../types/agent';
import { getHealth } from '../api/logs';

export function useHealth(intervalMs = 30000) {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      setHealth(await getHealth());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backend injoignable');
    }
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer === null) {
        refresh();
        timer = setInterval(refresh, intervalMs);
      }
    };
    const stop = () => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [refresh, intervalMs]);

  return { health, error, refresh };
}
