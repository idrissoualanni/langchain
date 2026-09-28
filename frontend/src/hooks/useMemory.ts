// Hook Memory — mémoire longue durée de l'utilisateur (profil + MemoryFacts v3).
// La partie thread-scopée (state LangGraph / checkpoints) a été retirée avec
// la page admin « Mémoire » ; ce hook ne dépend plus que du user.
import { useCallback, useEffect, useState } from 'react';
import type {
  MemoryFact,
  MemoryOverview,
  UserProfile,
} from '../types/agent';
import {
  createMemoryFact,
  deleteMemoryFact,
  getMemoryOverview,
  updateMemoryFact,
  updateUserProfile,
} from '../api/memory';

export function useMemory(userId?: string | null) {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [overview, setOverview] = useState<MemoryOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // Mémoire longue durée : ne dépend que du user — pas du thread
    if (!userId) {
      setOverview(null);
      setProfile(null);
      return;
    }
    setLoading(true);
    try {
      setError(null);
      const mem = await getMemoryOverview(userId).catch(() => null);
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
  }, [userId]);

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
