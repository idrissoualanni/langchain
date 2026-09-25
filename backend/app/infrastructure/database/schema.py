"""Schéma PostgreSQL des tables applicatives sur Neon.

Tables créées de façon IDEMPOTENTE au démarrage ( init_schema() ),
uniquement en mode PostgreSQL. Elles n'écrasent JAMAIS de données
existantes : CREATE TABLE IF NOT EXISTS + ALTER TABLE ADD COLUMN
seulement si la colonne manque ( cf. connections.MIGRATIONS ).

Tables :
  object_storage    binaires uploadés ( documents, images, vidéos )
  videos            métadonnées + transcript des vidéos traitées
  video_segments    segments pédagogiques + embedding pgvector
  calendar_events   agenda du serveur MCP calendar
  mcp_files         fichiers du serveur MCP filesystem ( 100% en base )
  mcp_file_versions historique des écrasements mcp_files
  knowledge_sections corpus statique indexé ( cache des 70 Markdown )

La dimension des colonnes vector(dim) est celle du provider d'embedding
actif ( embeddings.yaml ). Un changement de modèle de nécessite une
réindexation — documenté dans la mémoire du projet.
"""
from __future__ import annotations

from app.config import DATABASE_URL, USE_POSTGRES
from app.logging.events import log_event

# Limite de dimension pgvector ( docs : max 16000 ).
_PGVECTOR_MAX_DIM = 16_000

# Extension + tables ( la dimension vector est substituée à l'init ).
_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector;"

_TABLES = [
    # ---------------------------------------------------------------
    # Binaires uploadés — octets sur Neon Storage ( S3 ), métadonnées
    # en base. s3_key = clé S3 ( NULL si les octets sont en BYTEA :
    # fallback quand S3 est indisponible ). Déduplication par sha256
    # ( UNIQUE par utilisateur : deux users peuvent uploader le même
    # fichier sans se gêner ).
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS object_storage (
        object_id    TEXT PRIMARY KEY,
        user_id      TEXT NOT NULL,
        kind         TEXT NOT NULL,
        filename     TEXT NOT NULL,
        mime         TEXT NOT NULL,
        size_bytes   BIGINT NOT NULL,
        content      BYTEA,
        sha256       TEXT NOT NULL,
        s3_key       TEXT,
        created_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_object_storage_user_kind "
    "ON object_storage(user_id, kind)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_object_storage_sha "
    "ON object_storage(user_id, sha256)",

    # ---------------------------------------------------------------
    # Vidéo — knowledge store ( remplace les JSON du dossier temporaire )
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS videos (
        video_id        TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        filename        TEXT NOT NULL,
        source_url      TEXT NOT NULL DEFAULT '',
        duration        DOUBLE PRECISION NOT NULL DEFAULT 0,
        knowledge_key   TEXT NOT NULL,
        transcript      TEXT NOT NULL DEFAULT '',
        media_object_id TEXT REFERENCES object_storage(object_id) ON DELETE SET NULL,
        created_at      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_videos_user ON videos(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_videos_knowledge_key ON videos(knowledge_key)",

    # ---------------------------------------------------------------
    # Segments pédagogiques — embedding pgvector pour la recherche
    # sémantique ( lexical conservé en complément, cf. retrieval ).
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS video_segments (
        id          BIGSERIAL PRIMARY KEY,
        video_id    TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
        idx         INTEGER NOT NULL,
        title       TEXT NOT NULL DEFAULT '',
        summary     TEXT NOT NULL DEFAULT '',
        start       DOUBLE PRECISION NOT NULL DEFAULT 0,
        "end"       DOUBLE PRECISION NOT NULL DEFAULT 0,
        topics      JSONB NOT NULL DEFAULT '[]'::jsonb,
        embedding   vector(__DIM__),
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_video_segments_video "
    "ON video_segments(video_id)",
    "CREATE INDEX IF NOT EXISTS idx_video_segments_embedding "
    "ON video_segments USING hnsw (embedding vector_cosine_ops)",

    # ---------------------------------------------------------------
    # MCP calendar — agenda global ( user_id NULL = legacy, jamais
    # rattaché arbitrairement ; les nouveaux events prennent l'user ).
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS calendar_events (
        id          TEXT PRIMARY KEY,
        title       TEXT NOT NULL,
        start       TEXT NOT NULL,
        "end"       TEXT NOT NULL,
        created     TEXT NOT NULL,
        user_id     TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_calendar_events_user ON calendar_events(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start)",

    # ---------------------------------------------------------------
    # MCP filesystem — 100% en base, ZÉRO fichier sur disque.
    # UNIQUE (user_id, path) : isolation stricte entre utilisateurs.
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS mcp_files (
        file_id     TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        path        TEXT NOT NULL,
        content     TEXT NOT NULL,
        sha256      TEXT NOT NULL,
        bytes_size  BIGINT NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_files_user_path "
    "ON mcp_files(user_id, path)",
    "CREATE INDEX IF NOT EXISTS idx_mcp_files_user ON mcp_files(user_id)",
    """
    CREATE TABLE IF NOT EXISTS mcp_file_versions (
        version_id  BIGSERIAL PRIMARY KEY,
        file_id     TEXT NOT NULL REFERENCES mcp_files(file_id) ON DELETE CASCADE,
        content     TEXT NOT NULL,
        bytes_size  BIGINT NOT NULL DEFAULT 0,
        sha256      TEXT NOT NULL,
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mcp_file_versions_file "
    "ON mcp_file_versions(file_id)",

    # ---------------------------------------------------------------
    # Corpus knowledge — cache indexé des 70 Markdown ( source de
    # vérité = le dossier versionné ; Neon = index de recherche ).
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS knowledge_sections (
        id              BIGSERIAL PRIMARY KEY,
        subject_id      TEXT NOT NULL,
        topic_slug      TEXT NOT NULL,
        title           TEXT NOT NULL,
        content         TEXT NOT NULL,
        embedding       vector(__DIM__),
        source_sha      TEXT NOT NULL,
        created_at      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_knowledge_sections_subject "
    "ON knowledge_sections(subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_knowledge_sections_sha "
    "ON knowledge_sections(source_sha)",
    "CREATE INDEX IF NOT EXISTS idx_knowledge_sections_embedding "
    "ON knowledge_sections USING hnsw (embedding vector_cosine_ops)",
]


def _pg_url() -> str:
    """URL SQLAlchemy psycopg3 ( cf. persistence._postgres_url )."""
    scheme, rest = DATABASE_URL.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return DATABASE_URL


def _embedding_dim() -> int:
    """Dimension effective du provider d'embedding actif.

    pgvector exige une dimension déclarée pour vector(dim) ; on prend
    donc celle du provider ( embeddings.yaml ) plutôt qu'une constante.
    Probe sur un texte court — un échec est sans gravité : les colonnes
    vector sont créées à la dimension max autorisée et l'insert CAST
    adapté ( cf. vector_store._vec_literal ) ne dépend pas de cette
    valeur. On ne fait JAMAIS échouer le démarrage pour cela.
    """
    try:
        from app.services.context.semantic.provider import (
            get_embedding_provider,
        )

        provider = get_embedding_provider()
        return min(len(provider.embed_text("dimension probe")), _PGVECTOR_MAX_DIM)
    except Exception:
        # Fiable et inoffensif : la dimension max acceptée par pgvector.
        return _PGVECTOR_MAX_DIM


def init_schema() -> None:
    """Crée extension + tables applicatives sur Neon ( idempotent ).

    À appeler au démarrage après init_db()/init_persistence(). Ne lève
    jamais sur une table déjà existante ( IF NOT EXISTS partout ).
    """
    if not (USE_POSTGRES and DATABASE_URL):
        return

    from sqlalchemy import create_engine, inspect, text

    dim = _embedding_dim()
    engine = create_engine(_pg_url(), pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(_EXTENSION))
            for stmt in _TABLES:
                # Les colonnes vector() sont créées à la dimension du
                # provider actif ( embeddings.yaml ) — pas une constante.
                conn.execute(text(stmt.replace("__DIM__", str(dim))))
            # -----------------------------------------------------------
            # Migrations ADDITIVES idempotentes ( cf. connections.
            # MIGRATIONS ) : on ajoute une colonne seulement si elle
            # manque. Aucune donnée existante n'est modifiée ou
            # supprimée.
            # -----------------------------------------------------------
            insp = inspect(conn)
            if insp.has_table("object_storage"):
                cols = {
                    c["name"] for c in insp.get_columns("object_storage")
                }
                if "s3_key" not in cols:
                    conn.execute(
                        text("ALTER TABLE object_storage ADD COLUMN s3_key TEXT")
                    )
                # content NOT NULL → nullable : les objets stockés en S3
                # n'ont pas d'octets en base. ALTER sans toucher aux
                # valeurs existantes.
                if "content" in cols:
                    conn.execute(
                        text("ALTER TABLE object_storage ALTER COLUMN content DROP NOT NULL")
                    )
        log_event(
            "NEON_SCHEMA_INIT",
            message=(
                "Tables applicatives créées/vérifiées sur Neon "
                f"| vector_dim={dim}"
            ),
        )
    finally:
        engine.dispose()


__all__ = ["init_schema", "_embedding_dim"]
