"""Stockage binaire — Neon Storage ( S3-compatible ) pour les octets,
Neon PostgreSQL pour les métadonnées.

Architecture :
  - Les OCTETS vont sur Neon Storage ( S3 : images, vidéos, documents ) ;
  - les MÉTADonnées ( filename, mime, taille, sha256, clé S3 ) vont dans
    object_storage ( PostgreSQL ), avec la clé de l'objet S3 en colonne.

Cela sépare le volume ( S3, pas cher, illimité ) de l'indexation (
PostgreSQL : recherche, listing, ownership ). La déduplication par
sha256 est conservée : deux uploads du même contenu par le même
utilisateur réutilisent l'objet existant.

Fallback BYTEA : si S3 n'est pas configuré ( clés absentes ) mais que
PostgreSQL l'est, les octets vont dans la colonne content. Sinon :
ObjectStorageError. Aucun store ne retombe silencieusement sur disque.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone

from app.config import DATABASE_URL, USE_POSTGRES
from app.logging.events import log_event

# Limite d'upload ( octets ). Au-delà on refuse clairement.
MAX_UPLOAD_BYTES = int(
    os.getenv("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024))  # 200 Mo en S3
)

KINDS = ("document", "image", "video")

# Préfixes de clés S3 par kind ( isolation structurelle ).
_KIND_PREFIX = {"document": "documents", "image": "images", "video": "videos"}


class ObjectStorageError(Exception):
    """Erreur contrôlée du stockage binaire (jamais propagée brute)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pg_url() -> str:
    """URL SQLAlchemy psycopg3 ( cf. persistence._postgres_url )."""
    scheme, rest = DATABASE_URL.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return DATABASE_URL


def _engine():
    from sqlalchemy import create_engine

    return create_engine(_pg_url(), pool_pre_ping=True)


# ------------------------------------------------------------------
# Configuration S3 — Neon Storage
# ------------------------------------------------------------------


def _s3_config() -> dict | None:
    """Config S3 complète, ou None si désactivée ( clés absentes ).

    Une clé PRÉSENTE mais VIDE ne doit pas activer S3 : os.getenv renvoie
    "" dans ce cas, ce qui donnerait des appels signés avec un secret
    vide ( erreurs 403 sourdes ). Toutes les trois sont requises.
    """
    endpoint = os.getenv("AWS_ENDPOINT_URL_S3", "").strip()
    key_id = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    region = os.getenv("AWS_REGION", "").strip()
    bucket = os.getenv("NEON_S3_BUCKET", "assets").strip()
    if not (endpoint and key_id and secret):
        return None
    return {
        "endpoint": endpoint,
        "key_id": key_id,
        "secret": secret,
        "region": region or "eu-central-1",
        "bucket": bucket or "assets",
    }


def _s3_client():
    """Client boto3 vers Neon Storage ( endpoint custom )."""
    cfg = _s3_config()
    if cfg is None:
        raise ObjectStorageError("Stockage S3 non configuré")
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise ObjectStorageError(
            "boto3 non installé — ajoutez boto3 aux dépendances backend"
        ) from exc

    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["key_id"],
        aws_secret_access_key=cfg["secret"],
        region_name=cfg["region"],
        config=Config(s3={"addressing_style": "path"}),
    )


def _s3_key(kind: str, user_id: str, object_id: str, filename: str) -> str:
    """Clé S3 : <kind>/<user_id>/<object_id>/<filename>.

    Le user_id dans la clé ISOLE structurellement les objets ; l'accès
    reste contrôlé par PostgreSQL ( ownership ) — jamais de confiance
    accordée à la clé seule.
    """
    prefix = _KIND_PREFIX.get(kind, "other")
    # Nom de fichier SANITISÉ : on ne prend que le basename ( jamais de
    # chemin client — pas de traversal possible ) et on neutralise les
    # caractères spéciaux.
    safe_name = os.path.basename(filename or "").strip() or "bin"
    safe_name = "".join(
        c for c in safe_name if c.isalnum() or c in (".", "-", "_")
    ) or "bin"
    return f"{prefix}/{user_id}/{object_id}/{safe_name}"


def _ensure_bucket(client, bucket: str) -> None:
    """Crée le bucket s'il n'existe pas ( idempotent, erreurs ignorées
    pour les cas 403/409 — un bucket déjà existant n'est pas une erreur
    fatale ; l'upload échouera de toute façon s'il manque vraiment )."""
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        try:
            client.create_bucket(Bucket=bucket)
        except Exception:
            pass  # l'upload suivant donnera l'erreur réelle


# ------------------------------------------------------------------
# API publique
# ------------------------------------------------------------------


def put_object(
    *,
    user_id: str,
    kind: str,
    filename: str,
    mime: str,
    data: bytes,
) -> dict:
    """Stocke un binaire ( octets en S3, métadonnées en PostgreSQL ).

    Refuse : kind inconnu, contenu vide, contenu > MAX_UPLOAD_BYTES,
    user_id absent. Retourne {object_id, deduped, storage}.
    """
    if not (USE_POSTGRES and DATABASE_URL):
        raise ObjectStorageError(
            "Stockage binaire disponible uniquement en mode PostgreSQL (Neon)"
        )
    if kind not in KINDS:
        raise ObjectStorageError(
            f"kind inconnu : {kind}. Autorisés : {list(KINDS)}"
        )
    if not user_id:
        raise ObjectStorageError("user_id requis")
    if not data:
        raise ObjectStorageError("contenu vide")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ObjectStorageError(
            f"contenu > {MAX_UPLOAD_BYTES} octets — écriture refusée "
            "(MAX_UPLOAD_BYTES)."
        )

    sha = hashlib.sha256(data).hexdigest()

    from sqlalchemy import text

    cfg = _s3_config()
    engine = _engine()
    try:
        with engine.begin() as conn:
            # Dédup : même sha + même user → on réutilise l'objet.
            existing = conn.execute(
                text(
                    "SELECT object_id FROM object_storage "
                    "WHERE user_id = :uid AND sha256 = :sha"
                ),
                {"uid": user_id, "sha": sha},
            ).fetchone()
            if existing is not None:
                log_event(
                    "OBJECT_STORAGE_DEDUP",
                    message=f"Objet réutilisé | user={user_id} | sha={sha[:12]}",
                    user_id=user_id,
                )
                return {
                    "object_id": existing[0],
                    "deduped": True,
                    "storage": "s3" if cfg else "bytea",
                }

            object_id = uuid.uuid4().hex
            created = _now_iso()
            s3_key: str | None = None

            if cfg is not None:
                # ---- S3 : octets sur Neon Storage ----
                s3_key = _s3_key(kind, user_id, object_id, filename)
                try:
                    client = _s3_client()
                    _ensure_bucket(client, cfg["bucket"])
                    client.put_object(
                        Bucket=cfg["bucket"],
                        Key=s3_key,
                        Body=data,
                        ContentType=mime or "application/octet-stream",
                    )
                except Exception as exc:
                    # S3 en panne → on ne perd PAS l'upload : fallback
                    # BYTEA ( signalé dans storage ).
                    log_event(
                        "OBJECT_STORAGE_S3_FALLBACK",
                        level="WARNING",
                        message=(
                            f"S3 indisponible, fallback BYTEA | "
                            f"user={user_id} | {str(exc)[:120]}"
                        ),
                        user_id=user_id,
                    )
                    s3_key = None

            storage = "s3" if s3_key else "bytea"
            conn.execute(
                text(
                    """INSERT INTO object_storage
                       (object_id, user_id, kind, filename, mime,
                        size_bytes, content, sha256, s3_key, created_at)
                       VALUES (:oid, :uid, :kind, :filename, :mime,
                               :size, :content, :sha, :s3_key, :created)"""
                ),
                {
                    "oid": object_id,
                    "uid": user_id,
                    "kind": kind,
                    "filename": filename,
                    "mime": mime,
                    "size": len(data),
                    # BYTEA que si S3 n'a pas pris l'objet ( sinon NULL ).
                    "content": data if storage == "bytea" else None,
                    "sha": sha,
                    "s3_key": s3_key,
                    "created": created,
                },
            )
        return {
            "object_id": object_id,
            "deduped": False,
            "storage": storage,
        }
    finally:
        engine.dispose()


def get_object(object_id: str, user_id: str) -> dict | None:
    """Lit un binaire ( octets + métadonnées, ownership vérifiée ).

    Retourne None si absent ou si l'objet appartient à un autre user.
    """
    if not (USE_POSTGRES and DATABASE_URL):
        raise ObjectStorageError(
            "Stockage binaire disponible uniquement en mode PostgreSQL (Neon)"
        )
    if not object_id or not user_id:
        return None

    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT object_id, user_id, kind, filename, mime,
                              size_bytes, content, sha256, s3_key, created_at
                       FROM object_storage
                       WHERE object_id = :oid AND user_id = :uid"""
                ),
                {"oid": object_id, "uid": user_id},
            ).fetchone()
        if row is None:
            return None
        m = row._mapping
        data: bytes | None = None
        if m["s3_key"]:
            # ---- S3 : lecture depuis Neon Storage ----
            try:
                client = _s3_client()
                cfg = _s3_config()
                resp = client.get_object(
                    Bucket=cfg["bucket"], Key=m["s3_key"]
                )
                data = resp["Body"].read()
            except Exception as exc:
                log_event(
                    "OBJECT_STORAGE_S3_READ_ERROR",
                    level="ERROR",
                    message=(
                        f"Lecture S3 impossible | key={m['s3_key']} | "
                        f"{str(exc)[:120]}"
                    ),
                    user_id=user_id,
                )
                data = None
        if data is None and m["content"] is not None:
            data = bytes(m["content"])
        return {
            "object_id": m["object_id"],
            "user_id": m["user_id"],
            "kind": m["kind"],
            "filename": m["filename"],
            "mime": m["mime"],
            "size_bytes": m["size_bytes"],
            "content": data,
            "sha256": m["sha256"],
            "storage": "s3" if m["s3_key"] else "bytea",
            "created_at": m["created_at"],
        }
    finally:
        engine.dispose()


def list_objects(user_id: str, kind: str | None = None) -> list[dict]:
    """Liste les métadonnées ( sans le contenu ) d'un utilisateur."""
    if not (USE_POSTGRES and DATABASE_URL):
        raise ObjectStorageError(
            "Stockage binaire disponible uniquement en mode PostgreSQL (Neon)"
        )
    if not user_id:
        return []

    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.connect() as conn:
            if kind:
                rows = conn.execute(
                    text(
                        """SELECT object_id, kind, filename, mime,
                                  size_bytes, sha256, s3_key, created_at
                           FROM object_storage
                           WHERE user_id = :uid AND kind = :kind
                           ORDER BY created_at DESC"""
                    ),
                    {"uid": user_id, "kind": kind},
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        """SELECT object_id, kind, filename, mime,
                                  size_bytes, sha256, s3_key, created_at
                           FROM object_storage
                           WHERE user_id = :uid
                           ORDER BY created_at DESC"""
                    ),
                    {"uid": user_id},
                ).fetchall()
        return [
            {
                **dict(r._mapping),
                "storage": "s3" if r._mapping["s3_key"] else "bytea",
            }
            for r in rows
        ]
    finally:
        engine.dispose()


def delete_object(object_id: str, user_id: str) -> bool:
    """Supprime un binaire ( S3 + PostgreSQL, ownership vérifiée )."""
    if not (USE_POSTGRES and DATABASE_URL):
        raise ObjectStorageError(
            "Stockage binaire disponible uniquement en mode PostgreSQL (Neon)"
        )

    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.begin() as conn:
            # On lit la clé S3 AVANT de supprimer la ligne.
            row = conn.execute(
                text(
                    "SELECT s3_key FROM object_storage "
                    "WHERE object_id = :oid AND user_id = :uid"
                ),
                {"oid": object_id, "uid": user_id},
            ).fetchone()
            if row is None:
                return False
            s3_key = row[0]
            if s3_key:
                try:
                    client = _s3_client()
                    cfg = _s3_config()
                    client.delete_object(
                        Bucket=cfg["bucket"], Key=s3_key
                    )
                except Exception as exc:
                    # La ligne DB est supprimée quand même : un objet S3
                    # orphelin vaut mieux qu'un binaire fantôme que
                    # l'utilisateur croit supprimé. L'erreur est tracée.
                    log_event(
                        "OBJECT_STORAGE_S3_DELETE_ERROR",
                        level="WARNING",
                        message=(
                            f"Suppression S3 impossible | key={s3_key} | "
                            f"{str(exc)[:120]}"
                        ),
                        user_id=user_id,
                    )
            cur = conn.execute(
                text(
                    "DELETE FROM object_storage "
                    "WHERE object_id = :oid AND user_id = :uid"
                ),
                {"oid": object_id, "uid": user_id},
            )
        return cur.rowcount > 0
    finally:
        engine.dispose()


__all__ = [
    "MAX_UPLOAD_BYTES",
    "KINDS",
    "ObjectStorageError",
    "put_object",
    "get_object",
    "list_objects",
    "delete_object",
    "s3_configured",
]


def s3_configured() -> bool:
    """True si Neon Storage ( S3 ) est configuré et utilisable."""
    return _s3_config() is not None
