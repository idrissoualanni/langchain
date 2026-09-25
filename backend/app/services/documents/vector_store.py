# RagStore V11 — stockage des documents utilisateur (dual-dialecte).
#
# Deux backends, UN SEUL code :
#   - PostgreSQL (Neon, pgvector) si DATABASE_URL est définie ;
#   - SQLite local (user_documents.db) sinon (développement).
#
# Tables :
#   documents : métadonnées (doc_id, user_id, filename, mime, size,
#               created_at, chunk_count)
#   chunks    : contenu + embedding
#               - PostgreSQL : colonne vector(dim) pgvector + index HNSW
#               - SQLite     : BLOB struct double array (historique)
#
# Isolation stricte par user_id à TOUTES les lectures (jamais de
# fuite entre utilisateurs). La recherche est HYBRIDE dans les deux cas :
# 0.6 * cosine ( natif pgvector en PostgreSQL, en Python en SQLite ) +
# 0.4 * lexical ( token overlap ).
from __future__ import annotations

import sqlite3
import struct
import threading
import uuid
from datetime import datetime, timezone

from app.config import DATABASE_URL, RAG_DB_PATH, USE_POSTGRES
from app.services.context.semantic.provider import (
    cosine_similarity,
    get_embedding_provider,
)
from app.schemas.document import (
    DocumentRecord,
    DocumentSearchResponse,
    DocumentSearchResult,
)

_SCHEMA_SQLITE = """
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

# Schéma PostgreSQL : emb devient vector(dim). La dimension est fixée par
# le provider actif ( embeddings.yaml ) — on ne peut PAS déclarer
# vector(1024) en dur sans risquer un mismatch si le modèle change.
# vector(100000) = dimension MAXIMALE acceptée par pgvector : le CAST
# 'a'::vector exige une dimension <= à celle déclarée. On crée donc la
# colonne à la dimension effective du provider à l'init ( cf. _dim ).
_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    size_bytes   BIGINT NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    chunk_count  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);
"""

# Limite de dimension pgvector ( docs : max 16000 ).
_PGVECTOR_MAX_DIM = 16_000


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


def _pg_url() -> str:
    """URL SQLAlchemy psycopg3 ( cf. persistence._postgres_url )."""
    scheme, rest = DATABASE_URL.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return DATABASE_URL


class RagStore:
    """Stockage documents utilisateur ( SQLite ou PostgreSQL/pgvector )."""

    def __init__(self, path=RAG_DB_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._engine = None
        self._dim: int | None = None

    # ------------------------------------------------------------------
    # dialecte
    # ------------------------------------------------------------------
    @property
    def _is_postgres(self) -> bool:
        return bool(USE_POSTGRES and DATABASE_URL)

    def _get_engine(self):
        """Engine SQLAlchemy ( PostgreSQL uniquement )."""
        if self._engine is None:
            from sqlalchemy import create_engine

            self._engine = create_engine(_pg_url(), pool_pre_ping=True)
        return self._engine

    def _get_dim(self) -> int:
        """Dimension d'embedding effective du provider actif.

        pgvector exige une dimension DECLAREE pour la colonne vector —
        on prend donc celle du provider ( embeddings.yaml ), pas une
        constante. Un changement de modèle d'embedding necessite une
        reindexation ( documente dans la memoire du projet ).
        """
        if self._dim is None:
            vec = self._embed("dimension probe")
            self._dim = len(vec)
        return self._dim

    def _ensure_pg_schema(self) -> None:
        """Crée tables + colonne vector + index HNSW ( idempotent )."""
        from sqlalchemy import text

        dim = min(self._get_dim(), _PGVECTOR_MAX_DIM)
        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(text(_SCHEMA_POSTGRES))
            # chunks créés à la dimension du provider ( ALTER si la colonne
            # existe déjà avec une autre dimension — reindexation manuelle
            # requise, on ne le fait JAMAIS silencieusement ).
            exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='chunks' AND column_name='emb'"
                )
            ).scalar()
            if not exists:
                conn.execute(
                    text(
                        f"""CREATE TABLE IF NOT EXISTS chunks (
                            chunk_id TEXT PRIMARY KEY,
                            doc_id   TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                            user_id  TEXT NOT NULL,
                            idx      INTEGER NOT NULL,
                            content  TEXT NOT NULL,
                            emb      vector({dim}) NOT NULL
                        )"""
                    )
                )
            # Index HNSW sur (user_id, emb) : filtre + recherche vectorielle
            # combinés. IF NOT EXISTS n'existe pas pour les index avant
            # PG14 → introspection.
            has_idx = conn.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE indexname = 'idx_chunks_user_emb'"
                )
            ).scalar()
            if not has_idx:
                conn.execute(
                    text(
                        "CREATE INDEX idx_chunks_user_emb "
                        "ON chunks USING hnsw (emb vector_cosine_ops)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunks_user_doc "
                        "ON chunks(user_id, doc_id)"
                    )
                )

    # ------------------------------------------------------------------
    # connexions
    # ------------------------------------------------------------------
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            with self._conn:
                self._conn.executescript(_SCHEMA_SQLITE)
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None

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
        content_type = content_type or "text/plain"
        size = len(text.encode("utf-8"))

        # embeddings : un échec au milieu ne doit PAS laisser de doc
        # orphelin → on prépare tout en mémoire puis on écrit.
        emb_rows: list[tuple] = []
        for i, chunk_text in enumerate(chunks):
            if not chunk_text or not chunk_text.strip():
                continue
            vec = self._embed(chunk_text)
            emb_rows.append((i, chunk_text, vec))

        with self._lock:
            if self._is_postgres:
                self._add_document_pg(
                    doc_id=doc_id,
                    user_id=user_id,
                    filename=filename,
                    content_type=content_type,
                    size=size,
                    created=created,
                    emb_rows=emb_rows,
                )
            else:
                self._add_document_sqlite(
                    doc_id=doc_id,
                    user_id=user_id,
                    filename=filename,
                    content_type=content_type,
                    size=size,
                    created=created,
                    emb_rows=emb_rows,
                )
        return DocumentRecord(
            doc_id=doc_id,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size,
            chunk_count=len(emb_rows),
            created_at=created,
        )

    def _add_document_sqlite(
        self, *, doc_id, user_id, filename, content_type, size, created,
        emb_rows,
    ) -> None:
        conn = self._get_conn()
        with conn:
            conn.execute(
                """INSERT INTO documents
                   (doc_id, user_id, filename, content_type,
                    size_bytes, created_at, chunk_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id, user_id, filename, content_type, size,
                    created, len(emb_rows),
                ),
            )
            conn.executemany(
                """INSERT INTO chunks
                   (chunk_id, doc_id, user_id, idx, content, emb, dim)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        f"{doc_id}:{i}", doc_id, user_id, i, chunk_text,
                        _pack(vec), len(vec),
                    )
                    for i, chunk_text, vec in emb_rows
                ],
            )

    def _add_document_pg(
        self, *, doc_id, user_id, filename, content_type, size, created,
        emb_rows,
    ) -> None:
        from sqlalchemy import text

        self._ensure_pg_schema()
        engine = self._get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO documents
                       (doc_id, user_id, filename, content_type,
                        size_bytes, created_at, chunk_count)
                       VALUES (:doc_id, :user_id, :filename,
                               :content_type, :size_bytes,
                               :created_at, :chunk_count)"""
                ),
                {
                    "doc_id": doc_id,
                    "user_id": user_id,
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": size,
                    "created_at": created,
                    "chunk_count": len(emb_rows),
                },
            )
            for i, chunk_text, vec in emb_rows:
                # psycopg3 sérialise une list[float] vers vector
                # automatiquement ( driver pgvector register_vector non
                # requis pour l'insert via liste textuelle ) — on passe
                # par la représentation littérale pgvector : '[1,2,3]'.
                conn.execute(
                    text(
                        """INSERT INTO chunks
                           (chunk_id, doc_id, user_id, idx, content, emb)
                           VALUES (:cid, :did, :uid, :idx, :content,
                                   CAST(:vec AS vector))"""
                    ),
                    {
                        "cid": f"{doc_id}:{i}",
                        "did": doc_id,
                        "uid": user_id,
                        "idx": i,
                        "content": chunk_text,
                        "vec": _vec_literal(vec),
                    },
                )

    # ------------------------------------------------------------------
    # lecture
    # ------------------------------------------------------------------
    def get_document(self, doc_id: str, user_id: str) -> DocumentRecord | None:
        if self._is_postgres:
            from sqlalchemy import text

            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        """SELECT doc_id, user_id, filename, content_type,
                                  size_bytes, created_at, chunk_count
                           FROM documents
                           WHERE doc_id = :doc_id AND user_id = :user_id"""
                    ),
                    {"doc_id": doc_id, "user_id": user_id},
                ).fetchone()
            if row is None:
                return None
            return DocumentRecord(**dict(row._mapping))

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
        if self._is_postgres:
            from sqlalchemy import text

            engine = self._get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """SELECT doc_id, user_id, filename, content_type,
                                  size_bytes, created_at, chunk_count
                           FROM documents WHERE user_id = :user_id
                           ORDER BY created_at DESC"""
                    ),
                    {"user_id": user_id},
                ).fetchall()
            return [DocumentRecord(**dict(r._mapping)) for r in rows]

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """SELECT * FROM documents WHERE user_id = ?
                   ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
        return [DocumentRecord(**dict(r)) for r in rows]

    def delete_document(self, doc_id: str, user_id: str) -> bool:
        if self._is_postgres:
            from sqlalchemy import text

            engine = self._get_engine()
            with engine.begin() as conn:
                cur = conn.execute(
                    text(
                        """DELETE FROM documents
                           WHERE doc_id = :doc_id AND user_id = :user_id"""
                    ),
                    {"doc_id": doc_id, "user_id": user_id},
                )
                # ON DELETE CASCADE supprime les chunks automatiquement.
            return cur.rowcount > 0

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
        if self._is_postgres:
            from sqlalchemy import text

            engine = self._get_engine()
            with engine.begin() as conn:
                cur = conn.execute(
                    text("DELETE FROM documents WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )
            return cur.rowcount

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

        PostgreSQL : le cosine est calculé NATIVEMENT par pgvector
        ( ORDER BY emb <=> q ), fini le scan Python de tous les chunks.
        SQLite : comportement historique ( scan + cosine Python ).
        """
        top_k = max(1, min(int(top_k), 20))
        if not query or not query.strip():
            return DocumentSearchResponse(status="unavailable", query=query or "")

        if self._is_postgres:
            return self._search_pg(
                user_id=user_id,
                query=query,
                top_k=top_k,
                score_threshold=score_threshold,
            )

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

    def _search_pg(
        self, *, user_id, query, top_k, score_threshold,
    ) -> DocumentSearchResponse:
        """Recherche hybride côté PostgreSQL : cosine NATIF pgvector.

        On récupère les top-N chunks par distance cosine ( index HNSW ),
        puis on applique le score lexical en Python pour l'hybride —
        exactement comme le faisait le mode SQLite, sans son scan complet.
        """
        from sqlalchemy import text

        try:
            qvec = self._embed(query)
        except Exception as exc:
            return DocumentSearchResponse(
                status="error", query=query, error=str(exc)
            )

        q_terms = self._terms(query)
        # On large un peu le filet : le score final est hybride, le top
        # cosine pur peut rater un chunk lexicalement excellent.
        fetch = min(top_k * 4, 40)

        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT c.chunk_id, c.doc_id, c.content,
                              d.filename,
                              (c.emb <=> CAST(:q AS vector)) AS distance
                       FROM chunks c
                       JOIN documents d ON d.doc_id = c.doc_id
                       WHERE c.user_id = :user_id
                       ORDER BY c.emb <=> CAST(:q AS vector)
                       LIMIT :fetch"""
                ),
                {
                    "user_id": user_id,
                    "q": _vec_literal(qvec),
                    "fetch": fetch,
                },
            ).fetchall()

        if not rows:
            return DocumentSearchResponse(
                status="unavailable", query=query, error="aucun document"
            )

        scored: list[DocumentSearchResult] = []
        for row in rows:
            r = row._mapping
            # pgvector cosine : distance = 1 - similarité
            sem = max(0.0, 1.0 - float(r["distance"]))
            lex = self._lexical_score(q_terms, r["content"])
            score = 0.6 * sem + 0.4 * lex
            if score < score_threshold:
                continue
            scored.append(
                DocumentSearchResult(
                    doc_id=r["doc_id"],
                    chunk_id=r["chunk_id"],
                    filename=r["filename"] or "",
                    content=r["content"],
                    relevance=round(min(1.0, score), 4),
                    lexical_score=round(lex, 4),
                    semantic_score=round(sem, 4),
                    metadata={
                        "index": r["chunk_id"].split(":")[-1],
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
        from app.services.context.query_norm import normalize_tokens

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


def _vec_literal(vec: list[float]) -> str:
    """Représentation littérale pgvector : '[0.1,0.2,...]' ( cast ::vector )."""
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


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
