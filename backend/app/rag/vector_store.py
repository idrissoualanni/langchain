# RagStore V10 — stockage SQLite des documents utilisateur.
#
# Deux tables :
#   documents : métadonnées (doc_id, user_id, filename, mime,
#               size, created_at, chunk_count)
#   chunks    : contenu + embedding BLOB (struct double array),
#               index sur (user_id, doc_id)
#
# Isolation stricte par user_id à TOUTES les lectures (jamais de
# fuite entre utilisateurs). Aucun service externe — SQLite seul.
from __future__ import annotations

import sqlite3
import struct
import threading
import uuid
from datetime import datetime, timezone

from app.config import DATABASE_DIR
from app.context.semantic.provider import (
    cosine_similarity,
    get_embedding_provider,
)
from app.schemas.document import (
    DocumentRecord,
    DocumentSearchResponse,
    DocumentSearchResult,
)

RAG_DB_PATH = DATABASE_DIR / "user_documents.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    chunk_count  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id   TEXT NOT NULL,
    user_id  TEXT NOT NULL,
    idx      INTEGER NOT NULL,
    content  TEXT NOT NULL,
    emb      BLOB NOT NULL,
    dim      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_user_doc ON chunks(user_id, doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
"""


class RagStoreError(Exception):
    """Erreur contrôlée du stockage documents (jamais propagée brute)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}d", *vec)


def _unpack(blob: bytes) -> list[float]:
    if not blob:
        return []
    n = len(blob) // 8
    return list(struct.unpack(f"<{n}d", blob))


class RagStore:
    """Stockage documents utilisateur (SQLite, thread-safe)."""

    def __init__(self, path=RAG_DB_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # connexion / schéma
    # ------------------------------------------------------------------
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            with self._conn:
                self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # médiation embeddings (provider actif réutilisé)
    # ------------------------------------------------------------------
    def _embed(self, text: str) -> list[float]:
        try:
            provider = get_embedding_provider()
            return provider.embed_text(text)
        except Exception:
            # provider indisponible → élève une erreur contrôlée
            raise RagStoreError("embedding provider indisponible")

    # ------------------------------------------------------------------
    # écriture
    # ------------------------------------------------------------------
    def add_document(
        self,
        *,
        user_id: str,
        filename: str,
        content_type: str,
        text: str,
        chunks: list[str],
    ) -> DocumentRecord:
        """Indexe un document : 1 doc + N chunks (embeddings faits ici)."""
        if not user_id:
            raise RagStoreError("user_id requis")
        if not text or not text.strip():
            raise RagStoreError("contenu vide")
        if not chunks:
            raise RagStoreError("aucun chunk généré")

        doc_id = uuid.uuid4().hex
        created = _now_iso()

        # embeddings : un échec au milieu ne doit PAS laisser de doc
        # orphelin → on prépare tout en mémoire puis on écrit.
        emb_rows: list[tuple] = []
        for i, chunk_text in enumerate(chunks):
            if not chunk_text or not chunk_text.strip():
                continue
            vec = self._embed(chunk_text)
            emb_rows.append(
                (
                    f"{doc_id}:{i}",
                    doc_id,
                    user_id,
                    i,
                    chunk_text,
                    _pack(vec),
                    len(vec),
                )
            )

        with self._lock:
            conn = self._get_conn()
            with conn:
                conn.execute(
                    """INSERT INTO documents
                       (doc_id, user_id, filename, content_type,
                        size_bytes, created_at, chunk_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc_id,
                        user_id,
                        filename,
                        content_type or "text/plain",
                        len(text.encode("utf-8")),
                        created,
                        len(emb_rows),
                    ),
                )
                conn.executemany(
                    """INSERT INTO chunks
                       (chunk_id, doc_id, user_id, idx, content, emb, dim)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    emb_rows,
                )
        return DocumentRecord(
            doc_id=doc_id,
            user_id=user_id,
            filename=filename,
            content_type=content_type or "text/plain",
            size_bytes=len(text.encode("utf-8")),
            chunk_count=len(emb_rows),
            created_at=created,
        )

    # ------------------------------------------------------------------
    # lecture
    # ------------------------------------------------------------------
    def get_document(self, doc_id: str, user_id: str) -> DocumentRecord | None:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                """SELECT * FROM documents
                   WHERE doc_id = ? AND user_id = ?""",
                (doc_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return DocumentRecord(**dict(row))

    def list_documents(self, user_id: str) -> list[DocumentRecord]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """SELECT * FROM documents WHERE user_id = ?
                   ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
        return [DocumentRecord(**dict(r)) for r in rows]

    def delete_document(self, doc_id: str, user_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            with conn:
                cur = conn.execute(
                    """DELETE FROM documents
                       WHERE doc_id = ? AND user_id = ?""",
                    (doc_id, user_id),
                )
                conn.execute(
                    """DELETE FROM chunks WHERE doc_id = ? AND user_id = ?""",
                    (doc_id, user_id),
                )
            return cur.rowcount > 0

    def delete_all(self, user_id: str) -> int:
        """Supprime TOUS les documents d'un user (reset). Retourne le
        nombre de documents supprimés."""
        with self._lock:
            conn = self._get_conn()
            with conn:
                cur = conn.execute(
                    "DELETE FROM documents WHERE user_id = ?", (user_id,)
                )
                conn.execute(
                    "DELETE FROM chunks WHERE user_id = ?", (user_id,)
                )
            return cur.rowcount

    # ------------------------------------------------------------------
    # recherche hybride (lexical + sémantique)
    # ------------------------------------------------------------------
    def search(
        self,
        *,
        user_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.05,
    ) -> DocumentSearchResponse:
        """Recherche hybride contrôlée (statut 4-valeurs).

        Sémantique (cosine) 0.6 + lexical (token overlap) 0.4 →
        score composite filtré par `score_threshold`.
        """
        top_k = max(1, min(int(top_k), 20))
        if not query or not query.strip():
            return DocumentSearchResponse(status="unavailable", query=query or "")

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """SELECT chunk_id, doc_id, content, emb, dim
                   FROM chunks WHERE user_id = ?""",
                (user_id,),
            ).fetchall()
            doc_names = {
                r["doc_id"]: r["filename"]
                for r in conn.execute(
                    """SELECT doc_id, filename FROM documents
                       WHERE user_id = ?""",
                    (user_id,),
                ).fetchall()
            }

        if not rows:
            return DocumentSearchResponse(
                status="unavailable", query=query, error="aucun document"
            )

        # 1. embedding de la requête (échec → error contrôlé)
        try:
            qvec = self._embed(query)
        except Exception as exc:  # pragma: no cover — défensif
            return DocumentSearchResponse(
                status="error", query=query, error=str(exc)
            )

        # 2. candidats : requête tokenisée
        q_terms = self._terms(query)

        scored: list[DocumentSearchResult] = []
        for row in rows:
            chunk_vec = _unpack(row["emb"])
            sem = cosine_similarity(qvec, chunk_vec)
            lex = self._lexical_score(q_terms, row["content"])
            score = 0.6 * sem + 0.4 * lex
            if score < score_threshold:
                continue
            scored.append(
                DocumentSearchResult(
                    doc_id=row["doc_id"],
                    chunk_id=row["chunk_id"],
                    filename=doc_names.get(row["doc_id"], ""),
                    content=row["content"],
                    relevance=round(min(1.0, score), 4),
                    lexical_score=round(lex, 4),
                    semantic_score=round(sem, 4),
                    metadata={
                        "index": row["chunk_id"].split(":")[-1],
                    },
                )
            )

        if not scored:
            return DocumentSearchResponse(
                status="insufficient", query=query
            )

        scored.sort(key=lambda r: r.relevance, reverse=True)
        return DocumentSearchResponse(
            status="found",
            query=query,
            results=scored[:top_k],
        )

    # ------------------------------------------------------------------
    # utilitaires terminologiques (cohérence query_norm)
    # ------------------------------------------------------------------
    @staticmethod
    def _terms(text: str) -> set[str]:
        from app.context.query_norm import normalize_tokens

        return set(t for t in normalize_tokens(text) if len(t) >= 2)

    @staticmethod
    def _lexical_score(q_terms: set[str], content: str) -> float:
        """Score lexical simple : proportion de tokens requête
        présents dans le contenu (normalisé, accents pliés)."""
        if not q_terms:
            return 0.0
        c_terms = RagStore._terms(content)
        if not c_terms:
            return 0.0
        hits = q_terms & c_terms
        return min(1.0, len(hits) / len(q_terms))


# ----------------------------------------------------------------------
# Singleton partagé (comme les stores existants du projet)
# ----------------------------------------------------------------------
_rag_store: RagStore | None = None
_rag_store_lock = threading.Lock()


def get_rag_store() -> RagStore:
    global _rag_store
    with _rag_store_lock:
        if _rag_store is None:
            _rag_store = RagStore()
        return _rag_store


def reset_rag_store() -> None:
    """Remplace le store partagé (tests)."""
    global _rag_store
    with _rag_store_lock:
        if _rag_store is not None:
            _rag_store.close()
        _rag_store = None


__all__ = [
    "RAG_DB_PATH",
    "RagStore",
    "RagStoreError",
    "get_rag_store",
    "reset_rag_store",
]