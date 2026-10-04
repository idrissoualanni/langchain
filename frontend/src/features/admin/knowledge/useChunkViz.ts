// useChunkViz — charge la projection PCA 3D des chunks vectorisés (admin).
//
// Le backend ( app/services/knowledge/viz.py ) renvoie les coordonnées 3D
// ( PCA ), les arêtes kNN et le ratio de variance. Ce hook ne fait que
// récupérer/rafraîchir ces données ; le rendu vit dans ChunkEmbeddingViz3D.
import { useCallback, useEffect, useState } from 'react';
import { apiRequest } from '@/api/request';

export interface ChunkPoint {
  id: number;
  x: number;
  y: number;
  z: number;
  subject_id: string;
  topic_slug: string;
  title: string;
  author: string;
  source_label: string;
}

export interface ChunkEdge {
  source: number;
  target: number;
  distance: number;
}

export interface ChunkVizData {
  projection: string;
  points: ChunkPoint[];
  edges: ChunkEdge[];
  count: number;
  dim: number;
  explained_variance: number[];
  subject_id: string | null;
}

export function useChunkViz(subjectId?: string, limit = 2000) {
  const [data, setData] = useState<ChunkVizData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (subjectId) qs.set('subject_id', subjectId);
      qs.set('limit', String(limit));
      const res = await apiRequest(
        `/api/admin/knowledge/chunks/viz?${qs.toString()}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData((await res.json()) as ChunkVizData);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erreur inconnue');
    } finally {
      setLoading(false);
    }
  }, [subjectId, limit]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading, error, reload: load };
}
