// API Documents V10 — RAG utilisateur (upload / list / search / delete).
//
// Toutes les routes sont scalées sur le user courant
// (/api/users/{userId}/documents) — ownership validé côté backend.
// Aucune manipulation d'auth ici : token injecté par apiFetch.
import { apiFetch } from './base';

export interface UserDocument {
  doc_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
}

export interface DocumentSearchHit {
  doc_id: string;
  chunk_id: string;
  filename: string;
  source: string;
  content: string;
  relevance: number;
  lexical_score: number;
  semantic_score: number;
  metadata: Record<string, unknown>;
}

export interface DocumentSearchResponse {
  status: 'found' | 'insufficient' | 'unavailable' | 'error';
  query: string;
  error: string;
  results: DocumentSearchHit[];
}

export interface UploadDocumentInput {
  filename: string;
  content: string;
  content_type?: string;
}

export async function listDocuments(userId: string): Promise<UserDocument[]> {
  return apiFetch<UserDocument[]>(`/api/users/${userId}/documents`);
}

export async function uploadDocument(
  userId: string,
  input: UploadDocumentInput
): Promise<UserDocument> {
  return apiFetch<UserDocument>(`/api/users/${userId}/documents`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function deleteDocument(
  userId: string,
  docId: string
): Promise<{ deleted: boolean; doc_id: string }> {
  return apiFetch<{ deleted: boolean; doc_id: string }>(
    `/api/users/${userId}/documents/${docId}`,
    { method: 'DELETE' }
  );
}

export async function searchDocuments(
  userId: string,
  query: string,
  topK = 5
): Promise<DocumentSearchResponse> {
  const qs = `?q=${encodeURIComponent(query)}&top_k=${topK}`;
  return apiFetch<DocumentSearchResponse>(
    `/api/users/${userId}/documents/search${qs}`
  );
}