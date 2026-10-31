from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any

import uuid

from sqlalchemy import create_engine, text
from app.config import DATABASE_URL
from app.core.exceptions import AppMemoryError
from app.infrastructure.database.persistence import _postgres_url
from app.logging.events import log_event
from app.services.context.semantic.provider import get_embedding_provider

logger = logging.getLogger(__name__)

_TABLE = "user_cognitive_memories"
_COLUMNS = "id, content, metadata, memory_type, created_at, updated_at"
# Le profil est rangé comme un souvenir (metadata.type = 'profile') : il
# ne doit jamais apparaître parmi les faits.
_NOT_PROFILE = "COALESCE(metadata->>'type', '') <> 'profile'"


def embedding_model_id(provider: Any) -> str:
    """Identifiant de l'espace d'embedding : classe du provider + modèle.

    Deux modèles différents produisent des espaces incomparables, même à
    dimension égale : la recherche ne compare que des vecteurs du même
    espace (colonne `embedding_model`).
    """
    return f"{type(provider).__name__}:{getattr(provider, '_model', '')}"


def _vec_literal(vec: list[float]) -> str:
    return f"[{','.join(map(str, vec))}]"


def _as_uuid(value: str) -> str | None:
    """UUID normalisé, ou None si `value` n'en est pas un (→ introuvable)."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _row_to_memory(row: Any) -> dict:
    metadata = row[2]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return {
        "id": str(row[0]),
        "content": row[1],
        "metadata": metadata or {},
        "type": row[3],
        "created_at": _iso(row[4]),
        "updated_at": _iso(row[5]),
    }


class CognitiveStore:
    """
    Infrastructure vectorielle pour la mémoire cognitive.

    Gère le stockage et la récupération sémantique des souvenirs utilisateur
    via pgvector sur Neon.
    """

    def __init__(self):
        self._engine = None
        self._embedding_dim = None
        self._column_dim: int | None = None

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

    def _get_column_dim(self, conn) -> int | None:
        """Dimension déclarée de la colonne `embedding` (pgvector : atttypmod)."""
        if self._column_dim is None:
            row = conn.execute(text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = to_regclass(:t) AND attname = 'embedding'"
            ), {"t": _TABLE}).first()
            if row is not None and isinstance(row[0], int) and row[0] > 0:
                self._column_dim = int(row[0])
        return self._column_dim

    def _embed(self, conn, content: str) -> tuple[str, str]:
        """Embedding de `content` + identifiant de modèle — dimension vérifiée.

        Refuse explicitement un vecteur dont la dimension diffère de la
        colonne, plutôt que de le tronquer ou de le compléter : un vecteur
        ajusté à la taille de la colonne n'appartient plus au même espace
        que les autres, et la similarité cosinus perd tout sens.
        """
        provider = get_embedding_provider()
        vec = provider.embed_text(content)
        column_dim = self._get_column_dim(conn)
        if column_dim is not None and len(vec) != column_dim:
            log_event(
                "EMBEDDING_DIM_MISMATCH",
                level="ERROR",
                message=(
                    f"{_TABLE}.embedding est vector({column_dim}) mais le "
                    f"provider produit {len(vec)} dimensions — lancer "
                    "scripts/reembed_cognitive_memories.py"
                ),
            )
            raise AppMemoryError(
                f"Dimension d'embedding incompatible ({len(vec)} ≠ {column_dim})"
            )
        return _vec_literal(vec), embedding_model_id(provider)

    def save_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "fact",
        metadata: dict[str, Any] = None
    ) -> str:
        metadata = metadata or {}
        engine = self._get_engine()

        if engine is None:
            log_event("COGNITIVE_MEM_SAVE_FALLBACK", message=f"No DB URL, memory not persisted for {user_id}")
            return "fallback_id"

        try:
            with engine.begin() as conn:
                embedding_str, model = self._embed(conn, content)
                query = text("""
                    INSERT INTO user_cognitive_memories
                    (user_id, content, embedding, embedding_model, metadata, memory_type, updated_at)
                    VALUES (:user_id, :content, :embedding, :model, :metadata, :memory_type, :now)
                    RETURNING id
                """)
                result = conn.execute(query, {
                    "user_id": user_id,
                    "content": content,
                    "embedding": embedding_str,
                    "model": model,
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
            with engine.connect() as conn:
                embedding_str, model = self._embed(conn, query)
                # Seuls les vecteurs du MÊME espace sont comparables : les
                # lignes d'un ancien modèle attendent leur ré-embedding.
                sql = text(f"""
                    SELECT {_COLUMNS}, 1 - (embedding <=> :embedding) as score
                    FROM user_cognitive_memories
                    WHERE user_id = :user_id
                    AND embedding_model = :model
                    AND {_NOT_PROFILE}
                    AND 1 - (embedding <=> :embedding) >= :min_score
                    ORDER BY embedding <=> :embedding
                    LIMIT :limit
                """)
                result = conn.execute(sql, {
                    "user_id": user_id,
                    "embedding": embedding_str,
                    "model": model,
                    "min_score": min_score,
                    "limit": limit
                })

                memories = []
                for row in result:
                    memory = _row_to_memory(row)
                    memory["score"] = float(row[6])
                    memories.append(memory)

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

    def list_memories(
        self, user_id: str, memory_type: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Souvenirs d'un utilisateur, du plus récent au plus ancien (hors profil).

        Lecture SQL directe : lister n'est pas chercher. L'ancienne version
        passait par une recherche sémantique sur une requête vide, filtrée
        par un score minimum — elle renvoyait un sous-ensemble arbitraire.
        """
        engine = self._get_engine()
        if engine is None:
            return []
        type_filter = "AND memory_type = :memory_type" if memory_type else ""
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT {_COLUMNS} FROM user_cognitive_memories
                WHERE user_id = :user_id AND {_NOT_PROFILE} {type_filter}
                ORDER BY updated_at DESC
                LIMIT :limit
            """), {"user_id": user_id, "memory_type": memory_type, "limit": limit})
            return [_row_to_memory(r) for r in rows]

    def get_memory(self, user_id: str, memory_id: str) -> dict | None:
        """Un souvenir de CET utilisateur, ou None (absent ou d'autrui)."""
        mid = _as_uuid(memory_id)
        engine = self._get_engine()
        if mid is None or engine is None:
            return None
        with engine.connect() as conn:
            row = conn.execute(text(f"""
                SELECT {_COLUMNS} FROM user_cognitive_memories
                WHERE id = CAST(:id AS uuid) AND user_id = :user_id
            """), {"id": mid, "user_id": user_id}).first()
        return _row_to_memory(row) if row is not None else None

    def update_memory(
        self,
        user_id: str,
        memory_id: str,
        content: str | None = None,
        memory_type: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
    ) -> dict | None:
        """Modifie un souvenir EN PLACE (ré-embedding si le contenu change).

        Retourne le souvenir mis à jour, ou None s'il n'existe pas pour cet
        utilisateur. L'ancien repli « supprimer puis réenregistrer » ne
        supprimait rien (méthode absente) : chaque modification dupliquait.
        """
        current = self.get_memory(user_id, memory_id)
        if current is None:
            return None
        metadata = {**current["metadata"], **(metadata_patch or {})}
        engine = self._get_engine()
        with engine.begin() as conn:
            params: dict[str, Any] = {
                "id": current["id"],
                "user_id": user_id,
                "memory_type": memory_type or current["type"],
                "metadata": json.dumps(metadata),
                "now": datetime.now(timezone.utc),
            }
            set_embedding = ""
            if content is not None and content != current["content"]:
                params["content"] = content
                params["embedding"], params["model"] = self._embed(conn, content)
                set_embedding = ", embedding = :embedding, embedding_model = :model"
            else:
                params["content"] = current["content"]
            row = conn.execute(text(f"""
                UPDATE user_cognitive_memories
                SET content = :content, memory_type = :memory_type,
                    metadata = :metadata, updated_at = :now{set_embedding}
                WHERE id = CAST(:id AS uuid) AND user_id = :user_id
                RETURNING {_COLUMNS}
            """), params).first()
        log_event(
            "COGNITIVE_MEM_UPDATE",
            message=f"Cognitive memory updated | user={user_id}",
            user_id=user_id,
            extra={"memory_id": current["id"]},
        )
        return _row_to_memory(row) if row is not None else None

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """Supprime un souvenir de CET utilisateur. False s'il n'existe pas."""
        mid = _as_uuid(memory_id)
        engine = self._get_engine()
        if mid is None or engine is None:
            return False
        with engine.begin() as conn:
            deleted = conn.execute(text(
                "DELETE FROM user_cognitive_memories "
                "WHERE id = CAST(:id AS uuid) AND user_id = :user_id"
            ), {"id": mid, "user_id": user_id}).rowcount
        if deleted:
            log_event(
                "COGNITIVE_MEM_DELETE",
                message=f"Cognitive memory deleted | user={user_id}",
                user_id=user_id,
                extra={"memory_id": mid},
            )
        return bool(deleted)

    def latest_profile(self, user_id: str) -> dict | None:
        """Métadonnées du profil le plus récent (metadata.type = 'profile')."""
        engine = self._get_engine()
        if engine is None:
            return None
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT metadata FROM user_cognitive_memories
                WHERE user_id = :user_id AND metadata->>'type' = 'profile'
                ORDER BY updated_at DESC
                LIMIT 1
            """), {"user_id": user_id}).first()
        if row is None:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})

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
