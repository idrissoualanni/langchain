// Hook Threads — liste par user + création
import { useCallback, useEffect, useState } from 'react';
import type { Thread } from '../types/agent';
import { createThread, listThreads } from '../api/threads';

export function useThreads(userId: string | null) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Charger les threads automatiquement quand l'utilisateur change
  useEffect(() => {
    let cancelled = false;

    if (!userId) {
      setThreads([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    listThreads(userId)
      .then((list) => {
        if (!cancelled) setThreads(list);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : 'Erreur');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  const refresh = useCallback(async () => {
    if (!userId) {
      setThreads([]);
      return;
    }
    setLoading(true);
    try {
      setError(null);
      setThreads(await listThreads(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const create = useCallback(
    async (name: string): Promise<Thread> => {
      if (!userId) throw new Error('Aucun utilisateur sélectionné');
      const thread = await createThread(userId, name);
      await refresh();
      return thread;
    },
    [userId, refresh]
  );

  return { threads, loading, error, refresh, create, setThreads };
}
