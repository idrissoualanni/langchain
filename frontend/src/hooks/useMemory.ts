// Hook Memory — state + historique + profil + MemoryFacts v3
import { useCallback, useEffect, useState } from 'react';
import type {
  Checkpoint,
  MemoryFact,
  MemoryOverview,
  ThreadState,
  UserProfile,
} from '../types/agent';
import {
  createMemoryFact,
  deleteMemoryFact,
  getMemoryOverview,
  getThreadHistory,
  getThreadState,
  updateMemoryFact,
  updateUserProfile,
} from '../api/memory';

export function useMemory(threadId: string | null, userId?: string | null) {
  const [state, setState] = useState<ThreadState | null>(null);
  const [history, setHistory] = useState<Checkpoint[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // Mémoire longue durée : ne dépend que du user — pas du thread
    const memoryPromise = userId
      ? getMemoryOverview(userId).catch(() => null)
      : Promise.resolve(null);

    if (!threadId) {
      setState(null);
      setHistory([]);
      const mem = await memoryPromise;
      setOverview(mem);
      setProfile(
        mem
          ? {
              user_id: mem.user_id,
              name: mem.identity.name,
              description: mem.identity.description,
              exists:
                mem.identity.name !== null ||
                mem.identity.description !== null,
            }
          : null
      );
      return;
    }
    setLoading(true);
    try {
      setError(null);
      const [s, h, mem] = await Promise.all([
        getThreadState(threadId, userId ?? undefined),
        getThreadHistory(threadId, userId ?? undefined),
        memoryPromise,
      ]);
      setState(s);
      setHistory(h);
      setOverview(mem);
      setProfile(
        mem
          ? {
              user_id: mem.user_id,
              name: mem.identity.name,
              description: mem.identity.description,
              exists:
                mem.identity.name !== null ||
                mem.identity.description !== null,
            }
          : null
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur');
    } finally {
      setLoading(false);
    }
  }, [threadId, userId]);

  const updateProfile = useCallback(
    async (fields: { name?: string; description?: string }) => {
      if (!userId) return null;
      const updated = await updateUserProfile(userId, fields);
      setProfile(updated);
      return updated;
    },
    [userId]
  );

  // ---- MemoryFacts v3 ----

  const addFact = useCallback(
    async (fact: { category: string; content: string; confidence?: number }) => {
      if (!userId) return null;
      const created = await createMemoryFact(userId, fact);
      await refresh();
      return created;
    },
    [userId, refresh]
  );

  const editFact = useCallback(
    async (factId: string, fields: { content?: string; category?: string }) => {
      if (!userId) return null;
      const updated = await updateMemoryFact(userId, factId, fields);
      await refresh();
      return updated;
    },
    [userId, refresh]
  );

  const removeFact = useCallback(
    async (factId: string) => {
      if (!userId) return null;
      const res = await deleteMemoryFact(userId, factId);
      await refresh();
      return res;
    },
    [userId, refresh]
  );

  const facts: MemoryFact[] = overview
    ? Object.values(overview.facts_by_category).flat()
    : [];

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
    state,
    history,
    profile,
    overview,
    facts,
    loading,
    error,
    refresh,
    updateProfile,
    addFact,
    editFact,
    removeFact,
  };
}
