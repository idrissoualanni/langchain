// Hook Subjects — Subject Registry (backend), jamais hardcodé React.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { listSubjects } from '../api/subjects';
import type { SubjectInfo } from '../types/agent';

export function useSubjects() {
  const [subjects, setSubjects] = useState<SubjectInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSubjects(await listSubjects());
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Registre des matières indisponible'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const byId = useMemo(
    () => new Map(subjects.map((s) => [s.id, s])),
    [subjects]
  );

  return { subjects, byId, loading, error, refresh };
}

/** Nom lisible d'une matière depuis son id (fallback : id brut). */
export function subjectLabel(
  byId: Map<string, SubjectInfo>,
  id: string
): string {
  return byId.get(id)?.name ?? id;
}
