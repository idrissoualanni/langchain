# MCP filesystem store — fichiers en BASE, ZÉRO fichier sur disque.
#
# Le serveur MCP filesystem était la dernière zone d'ombre : il écrivait
# dans backend/data/workspace/files ( disque local, éphémère sur Render,
# perdu à chaque redéploiement ). Ce module bascule le contenu en base
# ( table mcp_files ) avec versionnement des écrasements, sans changer
# AUCUNE règle de sécurité du serveur ( §41 ) — la sandbox vit dans le
# path, pas dans le stockage :
#
#   1. racine imposée ( le path est validé AVANT d'atteindre la base ) ;
#   2. pas de traversal, pas d'absolu, pas de ~ ;
#   3. écriture <= MCP_FS_MAX_BYTES, lecture tronquée au-delà ;
#   4. extensions textuelles seules ;
#   5. isolation par user_id ( propagé en argv du subprocess stdio ).
#
# Postgres seulement : si DATABASE_URL est absent, on refuse poliment
# plutôt que de retomber sur disque — l'invariant "100% en base" ne
# supporte pas de fallback silencieux. Les tests locaux passent par la
# même base de dev ( DATABASE_URL pointée sur Neon ou Postgres local ).
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import text

from app.config import DATABASE_URL, USE_POSTGRES
from app.logging.events import log_event


class McpFsError(RuntimeError):
    """Erreur métier MCP filesystem ( remontée au serveur MCP )."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _conn():
    """Connexion SQLAlchemy vers Neon.

    Pas de pool global : le serveur MCP est un SUBPROCESS stdio — chaque
    appel de tool ouvre une connexion courte et la referme. Un pool
    mort-né ( subprocess tué entre deux appels ) serait pire.
    """
    if not (USE_POSTGRES and DATABASE_URL):
        raise McpFsError(
            "MCP filesystem requiert DATABASE_URL ( Postgres ) — "
            "aucun stockage disque n'est plus supporté."
        )
    from app.infrastructure.database.persistence import _postgres_url

    from sqlalchemy import create_engine

    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    return engine


# ------------------------------------------------------------------
# CRUD — appelé par les 4 tools du serveur MCP
# ------------------------------------------------------------------


def file_exists(user_id: str, path: str) -> bool:
    """Le fichier existe-t-il pour CET utilisateur ?"""
    engine = _conn()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT 1 FROM mcp_files "
                    "WHERE user_id = :uid AND path = :path "
                    # un fichier supprimé logiquement ne réapparaît pas
                    "AND deleted_at IS NULL"
                ),
                {"uid": user_id, "path": path},
            ).fetchone()
        return row is not None
    finally:
        engine.dispose()


def create_file(user_id: str, path: str, content: str) -> tuple[int, str]:
    """Crée un fichier : REFUSE si existe déjà ( écrasement implicite ).

    Retourne ( taille_octets, file_id ).
    """
    if file_exists(user_id, path):
        raise McpFsError(f"'{path}' existe déjà — write_file pour remplacer")
    size = len(content.encode("utf-8"))
    file_id = hashlib.sha256(
        f"{user_id}:{path}:{_now()}".encode()
    ).hexdigest()
    engine = _conn()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO mcp_files "
                    "(file_id, user_id, path, content, sha256, bytes_size, "
                    " created_at, updated_at, deleted_at) "
                    "VALUES (:fid, :uid, :path, :content, :sha, :size, "
                    "        :now, :now, NULL)"
                ),
                {
                    "fid": file_id, "uid": user_id, "path": path,
                    "content": content, "sha": _hash(content),
                    "size": size, "now": _now(),
                },
            )
        return size, file_id
    finally:
        engine.dispose()


def write_file(user_id: str, path: str, content: str) -> tuple[int, str, bool]:
    """Crée ou écrase — l'ANCIEN contenu est VERSIONNÉ, jamais perdu.

    Retourne ( taille_octets, file_id, existed ).
    """
    size = len(content.encode("utf-8"))
    sha = _hash(content)
    now = _now()
    engine = _conn()
    try:
        with engine.begin() as conn:
            existing = conn.execute(
                text(
                    "SELECT file_id, content FROM mcp_files "
                    "WHERE user_id = :uid AND path = :path "
                    "AND deleted_at IS NULL FOR UPDATE"
                ),
                {"uid": user_id, "path": path},
            ).fetchone()

            if existing is None:
                file_id = hashlib.sha256(
                    f"{user_id}:{path}:{now}".encode()
                ).hexdigest()
                conn.execute(
                    text(
                        "INSERT INTO mcp_files "
                        "(file_id, user_id, path, content, sha256, "
                        " bytes_size, created_at, updated_at, deleted_at) "
                        "VALUES (:fid, :uid, :path, :content, :sha, :size, "
                        "        :now, :now, NULL)"
                    ),
                    {
                        "fid": file_id, "uid": user_id, "path": path,
                        "content": content, "sha": sha, "size": size,
                        "now": now,
                    },
                )
                return size, file_id, False

            file_id = existing[0]
            old_content = existing[1]
            # versionne l'ancien contenu ( convention pédagogique :
            # jamais de perte de données silencieuse )
            if old_content is not None:
                conn.execute(
                    text(
                        "INSERT INTO mcp_file_versions "
                        "(file_id, content, bytes_size, sha256, created_at) "
                        "VALUES (:fid, :content, :size, :sha, :now)"
                    ),
                    {
                        "fid": file_id, "content": old_content,
                        "size": len(old_content.encode("utf-8")),
                        "sha": _hash(old_content), "now": now,
                    },
                )
            conn.execute(
                text(
                    "UPDATE mcp_files SET content = :content, sha256 = :sha, "
                    "bytes_size = :size, updated_at = :now "
                    "WHERE file_id = :fid"
                ),
                {
                    "fid": file_id, "content": content, "sha": sha,
                    "size": size, "now": now,
                },
            )
        return size, file_id, True
    finally:
        engine.dispose()


def read_file(user_id: str, path: str) -> str:
    """Lit le contenu — McpFsError si absent ou supprimé."""
    engine = _conn()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT content FROM mcp_files "
                    "WHERE user_id = :uid AND path = :path "
                    "AND deleted_at IS NULL"
                ),
                {"uid": user_id, "path": path},
            ).fetchone()
        if row is None:
            raise McpFsError(f"'{path}' introuvable")
        content = row[0]
        if content is None:
            raise McpFsError(f"'{path}' est vide ( contenu absent )")
        return content
    finally:
        engine.dispose()


def list_files(user_id: str, prefix: str | None = None, limit: int = 200) -> list[str]:
    """Liste les chemins sous un préfixe ( '.' = tout ).

    Le listing est borné à `limit` ( §41 : pas de flooding du contexte ).
    Un répertoire n'existe pas en base : il est IMPLICITE dans les
    chemins — on reconstruit donc l'arbre à partir des fichiers.
    """
    engine = _conn()
    try:
        with engine.connect() as conn:
            if prefix and prefix != ".":
                rows = conn.execute(
                    text(
                        "SELECT path FROM mcp_files "
                        "WHERE user_id = :uid AND deleted_at IS NULL "
                        "AND path LIKE :prefix ESCAPE '\\' "
                        "ORDER BY path LIMIT :limit"
                    ),
                    {
                        "uid": user_id,
                        # LIKE avec échappement : "devoir%" sous la racine
                        "prefix": prefix.rstrip("/") + "/%",
                        "limit": limit + 1,
                    },
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        "SELECT path FROM mcp_files "
                        "WHERE user_id = :uid AND deleted_at IS NULL "
                        "ORDER BY path LIMIT :limit"
                    ),
                    {"uid": user_id, "limit": limit + 1},
                ).fetchall()
        return [r[0] for r in rows[:limit]]
    finally:
        engine.dispose()


def delete_file(user_id: str, path: str) -> bool:
    """Suppression logique — le contenu reste en mcp_file_versions."""
    engine = _conn()
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE mcp_files SET deleted_at = :now "
                    "WHERE user_id = :uid AND path = :path "
                    "AND deleted_at IS NULL"
                ),
                {"uid": user_id, "path": path, "now": _now()},
            )
        deleted = res.rowcount > 0
        if deleted:
            log_event(
                "MCP_FILE_DELETED",
                message=f"MCP file supprimé | user={user_id} | path={path}",
                user_id=user_id,
            )
        return deleted
    finally:
        engine.dispose()


__all__ = [
    "McpFsError",
    "file_exists",
    "create_file",
    "write_file",
    "read_file",
    "list_files",
    "delete_file",
]
