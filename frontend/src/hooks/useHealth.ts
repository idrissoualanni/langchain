// Hook Health — statuts Ollama / LangGraph / SQLite
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
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { health, error, refresh };
}
