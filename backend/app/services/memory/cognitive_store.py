from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlalchemy import create_engine, text
from app.config import DATABASE_URL
from app.infrastructure.database.persistence import _postgres_url
from app.logging.events import log_event
from app.services.context.semantic.provider import get_embedding_provider

logger = logging.getLogger(__name__)

# Dimension déclarée de la colonne vector() de user_cognitive_memories.
# Celle-ci a été créée à 1536 (provider de l'époque) ; le provider
# actuel (gemma4:31b-cloud via Ollama Cloud) produit 1024 dimensions.
# L'INSERT psycopg exige une correspondance exacte → padding à cette
# constante (voir _pad_embedding).
_COLUMN_DIM = 1536


def _pad_embedding(vec: list[float], dim: int) -> list[float]:
    """Borne un vecteur à `dim` dimensions (troncature ou padding zéro).

    Le padding zéro ne modifie PAS la similarité cosinus : un zéro ne
    contribue ni au produit scalaire ni à la norme L2.
    """
    if len(vec) >= dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


class CognitiveStore:
    """
    Infrastructure vectorielle pour la mémoire cognitive.

    Gère le stockage et la récupération sémantique des souvenirs utilisateur
    via pgvector sur Neon.
    """

    def __init__(self):
        self._engine = None
        self._embedding_dim = None

    def _get_engine(self):
        if self._engine is None:
            if not DATABASE_URL:
                return None
            self._engine = create_engine(_postgres_url(), pool_pre_ping=True)
        return self._engine

    def _get_current_dim(self) -> int:
        if self._embedding_dim is None:
            provider = get_embedding_provider()
            sample = provider.embed_text("dim")
            self._embedding_dim = len(sample)
        return self._embedding_dim

    def save_memory(
        self,
        user_id: str,
        content: str,
        memory_type: Literal["fact", "preference", "experience"] = "fact",
        metadata: dict[str, Any] = None
    ) -> str:
        metadata = metadata or {}
        engine = self._get_engine()

        if engine is None:
            log_event("COGNITIVE_MEM_SAVE_FALLBACK", message=f"No DB URL, memory not persisted for {user_id}")
            return "fallback_id"

        try:
            provider = get_embedding_provider()
            embedding = provider.embed_text(content)
            # Dimension déclarée de la colonne (vector(1536) à la
            # création). Un provider qui produit moins de dimensions
            # (ex: gemma4:31b-cloud = 1024) fait échouer l'INSERT
            # psycopg ("expected 1536 dimensions, not 1024"). On
            # padde avec des zéros jusqu'à la dimension de la colonne
            # — la similarité cosinus n'est pas affectée (le zéro ne
            # contribue ni au produit scalaire ni à la norme).
            embedding = _pad_embedding(embedding, _COLUMN_DIM)
            embedding_str = f"[{','.join(map(str, embedding))}]"

            with engine.begin() as conn:
                query = text("""
                    INSERT INTO user_cognitive_memories
                    (user_id, content, embedding, metadata, memory_type, updated_at)
                    VALUES (:user_id, :content, :embedding, :metadata, :memory_type, :now)
                    RETURNING id
                """)
                result = conn.execute(query, {
                    "user_id": user_id,
                    "content": content,
                    "embedding": embedding_str,
                    "metadata": json.dumps(metadata) if isinstance(metadata, dict) else metadata,
                    "memory_type": memory_type,
                    "now": datetime.now(timezone.utc)
                })
                memory_id = result.scalar()

                log_event(
                    "COGNITIVE_MEM_WRITE",
                    message=f"Cognitive memory saved | user={user_id} | type={memory_type}",
                    user_id=user_id,
                    extra={"memory_id": memory_id, "type": memory_type}
                )
                return str(memory_id)
        except Exception as e:
            log_event(
                "COGNITIVE_MEM_WRITE_ERROR",
                level="ERROR",
                message=f"Failed to save cognitive memory for {user_id}: {e}",
                user_id=user_id
            )
            raise

    def retrieve_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        min_score: float = 0.5
    ) -> list[dict]:
        engine = self._get_engine()
        if engine is None:
            return []

        try:
            provider = get_embedding_provider()
            query_embedding = provider.embed_text(query)
            embedding_str = f"[{','.join(map(str, query_embedding))}]"

            with engine.connect() as conn:
                sql = text("""
                    SELECT content, metadata, memory_type, 1 - (embedding <=> :embedding) as score
                    FROM user_cognitive_memories
                    WHERE user_id = :user_id
                    AND 1 - (embedding <=> :embedding) >= :min_score
                    ORDER BY embedding <=> :embedding
                    LIMIT :limit
                """)
                result = conn.execute(sql, {
                    "user_id": user_id,
                    "embedding": embedding_str,
                    "min_score": min_score,
                    "limit": limit
                })

                memories = []
                for row in result:
                    memories.append({
                        "content": row[0],
                        "metadata": json.loads(row[1]) if isinstance(row[1], str) else row[1],
                        "type": row[2],
                        "score": float(row[3])
                    })

                log_event(
                    "COGNITIVE_MEM_READ",
                    message=f"Retrieved {len(memories)} cognitive memories for {user_id}",
                    user_id=user_id,
                    extra={"query": query[:50], "count": len(memories)}
                )
                return memories
        except Exception as e:
            log_event(
                "COGNITIVE_MEM_READ_ERROR",
                level="ERROR",
                message=f"Failed to retrieve cognitive memories for {user_id}: {e}",
                user_id=user_id
            )
            return []

    # --- Learning Map Implementation ---

    def update_concept_mastery(self, user_id: str, concept_slug: str, level: float) -> None:
        """
        Update or create the mastery level of a concept for a user.
        level: 0.0 (Not learned) to 1.0 (Mastered)
        """
        engine = self._get_engine()
        if engine is None:
            return

        try:
            with engine.begin() as conn:
                # Upsert mastery
                query = text("""
                    INSERT INTO user_learning_map (user_id, concept_slug, mastery_level, updated_at)
                    VALUES (:user_id, :concept_slug, :level, :now)
                    ON CONFLICT (user_id, concept_slug)
                    DO UPDATE SET mastery_level = EXCLUDED.mastery_level, updated_at = EXCLUDED.updated_at
                """)
                conn.execute(query, {
                    "user_id": user_id,
                    "concept_slug": concept_slug,
                    "level": level,
                    "now": datetime.now(timezone.utc)
                })

                log_event(
                    "LEARNING_MAP_UPDATE",
                    message=f"Concept mastery updated | user={user_id} | concept={concept_slug} | level={level}",
                    user_id=user_id,
                    extra={"concept_slug": concept_slug, "level": level}
                )
        except Exception as e:
            logger.error(f"Failed to update concept mastery for {user_id}: {e}")
            raise

    def get_user_learning_graph(self, user_id: str) -> dict[str, Any]:
        """
        Retrieve the full learning map for a user, including dependencies.
        """
        engine = self._get_engine()
        if engine is None:
            return {"concepts": [], "dependencies": []}

        try:
            with engine.connect() as conn:
                # Get concepts
                concepts_query = text("""
                    SELECT concept_slug, mastery_level, updated_at
                    FROM user_learning_map
                    WHERE user_id = :user_id
                """)
                concepts_res = conn.execute(concepts_query, {"user_id": user_id})

                concepts = [
                    {"slug": row[0], "level": float(row[1]), "updated_at": row[2]}
                    for row in concepts_res
                ]

                # Get dependencies
                deps_query = text("""
                    SELECT prerequisite_slug, concept_slug
                    FROM concept_dependencies
                """)
                deps_res = conn.execute(deps_query)

                dependencies = [
                    {"from": row[0], "to": row[1]}
                    for row in deps_res
                ]

                return {
                    "concepts": concepts,
                    "dependencies": dependencies
                }
        except Exception as e:
            logger.error(f"Failed to retrieve learning graph for {user_id}: {e}")
            raise

    def add_concept_dependency(self, prerequisite_slug: str, concept_slug: str) -> None:
        """
        Link a dependency between two concepts.
        """
        engine = self._get_engine()
        if engine is None:
            return

        try:
            with engine.begin() as conn:
                query = text("""
                    INSERT INTO concept_dependencies (prerequisite_slug, concept_slug)
                    VALUES (:pre, :concept)
                    ON CONFLICT DO NOTHING
                """)
                conn.execute(query, {"pre": prerequisite_slug, "concept": concept_slug})

                log_event(
                    "LEARNING_MAP_DEP_ADD",
                    message=f"Dependency added: {prerequisite_slug} -> {concept_slug}"
                )
        except Exception as e:
            logger.error(f"Failed to add concept dependency: {e}")
            raise

# Singleton instance
cognitive_store = CognitiveStore()
