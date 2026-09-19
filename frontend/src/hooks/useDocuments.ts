// Hook Documents V10 — documents personnels de l'utilisateur (RAG).
//
// Cycle de vie : list (mount) → upload → refresh ; delete ; search
// contrôlé (statut 4-valeurs backend, jamais de crash).
import { useCallback, useEffect, useState } from 'react';
import {
  deleteDocument,
  listDocuments,
  searchDocuments,
  uploadDocument,
  type DocumentSearchResponse,
  type DocumentSearchHit,
  type UserDocument,
} from '../api/documents';

export interface UploadStatus {
  state: 'idle' | 'uploading' | 'error';
  message?: string;
}

export function useDocuments(userId: string | null) {
  const [documents, setDocuments] = useState<UserDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadStatus>({ state: 'idle' });

  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [hits, setHits] = useState<DocumentSearchHit[]>([]);
  const [searchStatus, setSearchStatus] = useState<
    DocumentSearchResponse['status'] | null
  >(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!userId) {
      setDocuments([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setDocuments(await listDocuments(userId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Liste indisponible');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleUpload = useCallback(
    async (
      filename: string,
      content: string,
      contentType = 'text/plain'
    ) => {
      if (!userId) {
        setUpload({ state: 'error', message: 'Aucune session' });
        return;
      }
      setUpload({ state: 'uploading' });
      try {
        await uploadDocument(userId, {
          filename,
          content,
          content_type: contentType,
        });
        setUpload({ state: 'idle' });
        await refresh();
      } catch (e) {
        setUpload({
          state: 'error',
          message: e instanceof Error ? e.message : "Échec de l'upload",
        });
      }
    },
    [userId, refresh]
  );

  const handleDelete = useCallback(
    async (docId: string) => {
      if (!userId) return;
      try {
        await deleteDocument(userId, docId);
        await refresh();
      } catch (e) {
        setError(
          e instanceof Error ? e.message : 'Suppression impossible'
        );
      }
    },
    [userId, refresh]
  );

  const handleSearch = useCallback(
    async (q: string) => {
      if (!userId || !q.trim()) {
        setHits([]);
        setSearchStatus(null);
        return;
      }
      setSearching(true);
      setSearchError(null);
      setQuery(q);
      try {
        const resp = await searchDocuments(userId, q, 5);
        setHits(resp.results);
        setSearchStatus(resp.status);
        if (resp.status === 'error') setSearchError(resp.error);
      } catch (e) {
        setSearchStatus('error');
        setSearchError(
          e instanceof Error ? e.message : 'Recherche impossible'
        );
      } finally {
        setSearching(false);
      }
    },
    [userId]
  );

  return {
    documents,
    loading,
    error,
    upload,
    refresh,
    uploadDocument: handleUpload,
    deleteDocument: handleDelete,
    query,
    setQuery,
    searching,
    hits,
    searchStatus,
    searchError,
    searchDocuments: handleSearch,
  };
}