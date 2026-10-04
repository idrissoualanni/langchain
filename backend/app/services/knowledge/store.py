# Knowledge Store — Neon pgvector, SEULE source du corpus de cours.
#
# Les fichiers Markdown `backend/app/knowledge/` ont été SUPPRIMÉS du
# dépôt ( mission : aucune base de connaissance codée en dur dans le
# projet ) : tout le corpus vit dans la table `knowledge_sections`
# ( contenu TEXT + embedding vector(1024) qwen3-embedding:0.6b ),
# remplie par la migration initiale.
#
# Deux accès, tous deux SANS repli fichier :
#   - search_semantic  : recherche vectorielle ( cosine HNSW ) —
#     consommé par knowledge_retriever.search_knowledge ( V6.5 ) ;
#   - get_section / match_section / list_topics : accès par sujet —
#     consommé par les tools pédagogiques ( référence d'exercice ).
#
# Cohérence OBLIGATOIRE index ↔ requête : la même config embeddings.yaml
# ( provider actif ) a servi à vectoriser le corpus ET vectorise les
# requêtes ici. Changer de modèle exige une ré-indexation ( force ).
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.logging.events import log_event

# Seuil de similarité cosinus minimale pour retenir une section.
# Cosine qwen3-embedding : contenu pertinent > 0.40 en pratique,
# bruit < 0.25 — 0.30 est le calepinage conservateur.
DEFAULT_MIN_SCORE = 0.30


def min_score() -> float:
    raw = os.getenv("KNOWLEDGE_SEMANTIC_MIN_SCORE", "").strip()
    if not raw:
        return DEFAULT_MIN_SCORE
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return DEFAULT_MIN_SCORE


@lru_cache(maxsize=1)
def _engine() -> Engine:
    from app.infrastructure.database.persistence import _postgres_url

    return create_engine(_postgres_url(), pool_pre_ping=True)


def _to_vector_literal(vector: list[float]) -> str:
    """List[float] → littéral pgvector '[0.1,0.2,…]' ( texte casté )."""
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"


def _embed(text_to_embed: str) -> list[float]:
    from app.services.context.semantic.provider import get_embedding_provider

    return get_embedding_provider().embed_text(text_to_embed)


def has_subject_corpus(subject_id: str) -> bool:
    """Le sujet a-t-il au moins une section indexée dans Neon ?"""
    with _engine().connect() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_sections "
                "WHERE subject_id = :sid"
            ),
            {"sid": subject_id},
        ).scalar_one()
    return n > 0


def list_topics(subject_id: str) -> list[str]:
    """Topics disponibles pour un sujet ( sections réelles, sans
    l'« _intro » ambiguë présente dans chaque fichier )."""
    with _engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT topic_slug FROM knowledge_sections "
                "WHERE subject_id = :sid AND topic_slug <> '_intro' "
                "ORDER BY topic_slug"
            ),
            {"sid": subject_id},
        ).fetchall()
    return [r[0] for r in rows]


def get_section(subject_id: str, topic_slug: str) -> dict | None:
    """Section EXACTE par slug ( comparaison sans accents ). Retour
    {source, topic, content} ou None — jamais inventé."""
    slug = _slugify(topic_slug)
    if not slug or slug == "_intro":
        return None
    with _engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT topic_slug, content, source_label "
                "FROM knowledge_sections "
                "WHERE subject_id = :sid AND topic_slug = :slug "
                "ORDER BY id LIMIT 1"
            ),
            {"sid": subject_id, "slug": slug},
        ).first()
    if row is None:
        return None
    return {
        "source": row[2] or subject_id,
        "topic": row[0],
        "content": row[1] or "",
    }


def match_section(subject_id: str, topic: str) -> dict | None:
    """Résout un topic ( Registry OU section ) vers une section réelle.

    Pont Registry ↔ knowledge ( ex-topic Registry « fonctions » →
    section « definition » du fichier fonctions ). Stratégie :
      1. slug exact ( comportement historique ) ;
      2. sous-chaîne dans le slug ou le titre de section ;
      3. repli sémantique : top-1 vectoriel au-dessus du seuil.
    Jamais d'invention : None si rien ne matche.
    """
    direct = get_section(subject_id, topic)
    if direct is not None:
        return direct

    needle = _slugify(topic)
    if needle:
        with _engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT topic_slug, content, source_label "
                    "FROM knowledge_sections "
                    "WHERE subject_id = :sid AND topic_slug <> '_intro' "
                    "AND (topic_slug LIKE :pat OR title ILIKE :pat) "
                    "ORDER BY id LIMIT 1"
                ),
                {"sid": subject_id, "pat": f"%{needle}%"},
            ).first()
        if row is not None and (row[1] or "").strip():
            return {
                "source": row[2] or subject_id,
                "topic": row[0],
                "content": row[1],
            }

    # Repli sémantique — le pont Registry passe par la proximité
    # vectorielle ( le topic « fonctions » colle à la section
    # « definition » du fichier Fonctions ).
    hits = search_semantic(subject_id, topic or "", limit=1)
    return (
        {
            "source": hits[0]["source"],
            "topic": hits[0]["topic"],
            "content": hits[0]["content"],
        }
        if hits
        else None
    )


def search_semantic(
    subject_id: str,
    query: str,
    limit: int = 3,
) -> list[dict]:
    """Recherche vectorielle ( cosine ) dans le corpus du sujet.

    Retour [{topic, title, content, source, relevance}] trié par
    pertinence décroissante, filtré au seuil min_score(). Le provider
    KO ou la table vide → liste vide + log ( pas d'exception : le
    caller décide du statut unavailable/insufficient ).
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        vector = _embed(q)
    except Exception as exc:
        log_event(
            "KNOWLEDGE_EMBED_ERROR",
            level="WARNING",
            message=f"Embedding requête impossible: {exc}",
            extra={"operation": "knowledge_semantic", "subject": subject_id},
        )
        return []

    qv = _to_vector_literal(vector)
    with _engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT topic_slug, title, content, source_label, "
                "1 - (embedding <=> CAST(:qv AS vector)) AS relevance "
                "FROM knowledge_sections "
                "WHERE subject_id = :sid "
                "ORDER BY embedding <=> CAST(:qv AS vector) "
                "LIMIT :k"
            ),
            {"sid": subject_id, "qv": qv, "k": int(limit)},
        ).fetchall()

    threshold = min_score()
    results = [
        {
            "topic": r[0],
            "title": r[1] or r[0],
            "content": r[2] or "",
            "source": r[3] or subject_id,
            "relevance": round(float(r[4]), 4),
        }
        for r in rows
        if r[2] and float(r[4]) >= threshold
    ]
    return results


def search_hybrid(
    subject_id: str,
    query: str,
    limit: int = 3,
    semantic_weight: float = 0.6,
) -> list[dict]:
    """Recherche HYBRIDE ( sémantique HNSW + lexical tsvector/GIN ).

    Combine, pour les mêmes candidates, la similarité cosinus
    ( `embedding <=> q`, index HNSW ) et le rang lexical
    (`ts_rank_cd(content_tsv, plainto_tsquery('french', q))`, index
    GIN). Score = w_sem·cosine + (1-w_sem)·lexical_normalisé.

    Les candidates sont d'abord bornées par l'index vectoriel ( top 3×
    limit ), puis re-classées par score hybride et filtrées au seuil
    min_score(). Provider KO / table vide → [] ( jamais d'exception,
    comme `search_semantic` ).

    Retour [{topic, title, content, source, author, relevance}].
    """
    q = (query or "").strip()
    if not q:
        return []
    try:
        vector = _embed(q)
    except Exception as exc:  # noqa: BLE001
        log_event(
            "KNOWLEDGE_EMBED_ERROR",
            level="WARNING",
            message=f"Embedding requête impossible (hybride): {exc}",
            extra={"operation": "knowledge_hybrid", "subject": subject_id},
        )
        return []

    qv = _to_vector_literal(vector)
    with _engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT topic_slug, title, content, source_label, author, "
                "1 - (embedding <=> CAST(:qv AS vector)) AS semantic, "
                "ts_rank_cd(content_tsv, plainto_tsquery('french', :q)) "
                "AS lexical "
                "FROM knowledge_sections "
                "WHERE subject_id = :sid "
                "ORDER BY embedding <=> CAST(:qv AS vector) "
                "LIMIT :k"
            ),
            {"sid": subject_id, "qv": qv, "q": q, "k": max(1, int(limit)) * 3},
        ).fetchall()

    if not rows:
        return []
    max_lex = max((float(r[6] or 0.0) for r in rows), default=0.0) or 1.0
    threshold = min_score()
    scored: list[tuple[float, tuple]] = []
    for r in rows:
        semantic = float(r[5] or 0.0)
        lexical = float(r[6] or 0.0) / max_lex
        score = semantic_weight * semantic + (1.0 - semantic_weight) * lexical
        scored.append((score, r))
    scored.sort(key=lambda t: t[0], reverse=True)

    out: list[dict] = []
    for score, r in scored[: max(1, int(limit))]:
        if score < threshold:
            continue
        out.append(
            {
                "topic": r[0],
                "title": r[1] or r[0],
                "content": r[2] or "",
                "source": r[3] or subject_id,
                "author": r[4] or "",
                "relevance": round(score, 4),
            }
        )
    return out


def upsert_section(
    subject_id: str,
    title: str,
    content: str,
    source_label: str | None = None,
    author: str = "",
) -> dict:
    """Crée ou remplace une section ( admin ) — vectorisation à l'écriture.

    Le slug est dérivé du titre ( même règle que le découpage historique
    `## Titre` ) : la recherche exacte et la recherche sémantique voient
    la section de façon identique au corpus migré. Une section existante
    de même ( subject_id, topic_slug ) est REMPLACÉE — pas de doublon.

    Retour {id, topic_slug, title, embedded} ; lève si le provider
    d'embedding échoue ( on n'insère JAMAIS une section sans vecteur :
    elle serait invisible de la recherche sémantique ).
    """
    slug = _slugify(title)
    if not slug or slug == "_intro":
        raise ValueError("Titre de section invalide ( slug vide ou '_intro' )")
    if not (content or "").strip():
        raise ValueError("Contenu de section vide")

    vector = _embed(f"{title}\n{content[:4000]}")
    if not vector:
        raise ValueError("Provider d'embedding: vecteur vide")

    with _engine().begin() as conn:
        conn.execute(
            text(
                "DELETE FROM knowledge_sections "
                "WHERE subject_id = :sid AND topic_slug = :slug"
            ),
            {"sid": subject_id, "slug": slug},
        )
        row = conn.execute(
            text(
                "INSERT INTO knowledge_sections "
                "(subject_id, topic_slug, title, content, embedding, "
                " source_sha, created_at, source_label, author) "
                "VALUES (:sid, :slug, :title, :content, "
                " CAST(:qv AS vector), :sha, :created, :label, :author) "
                "RETURNING id"
            ),
            {
                "sid": subject_id,
                "slug": slug,
                "title": (title or slug).strip(),
                "content": content.strip(),
                "qv": _to_vector_literal(vector),
                "sha": __import__("hashlib").sha256(
                    content.encode("utf-8")
                ).hexdigest(),
                "created": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
                "label": source_label or f"admin/{subject_id}",
                "author": author or "",
            },
        ).scalar_one()

    log_event(
        "KNOWLEDGE_SECTION_UPSERTED",
        message=f"Section admin | {subject_id}/{slug}",
        extra={
            "operation": "knowledge_upsert",
            "subject": subject_id,
            "topic": slug,
        },
    )
    return {
        "id": row,
        "subject_id": subject_id,
        "topic_slug": slug,
        "title": (title or slug).strip(),
        "embedded": True,
    }


def list_sections(subject_id: str | None = None) -> list[dict]:
    """Inventaire des sections ( admin ) — sans les vecteurs."""
    sql = (
        "SELECT id, subject_id, topic_slug, title, source_label, "
        "created_at, (embedding IS NOT NULL) AS embedded "
        "FROM knowledge_sections"
    )
    params: dict[str, str] = {}
    if subject_id:
        sql += " WHERE subject_id = :sid"
        params["sid"] = subject_id
    sql += " ORDER BY subject_id, topic_slug, id"
    with _engine().connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [
        {
            "id": r[0],
            "subject_id": r[1],
            "topic_slug": r[2],
            "title": r[3],
            "source_label": r[4],
            "created_at": r[5],
            "embedded": bool(r[6]),
        }
        for r in rows
    ]


def delete_section(section_id: int) -> bool:
    """Supprime une section par id ( admin ). Retour True si supprimée."""
    with _engine().begin() as conn:
        n = conn.execute(
            text("DELETE FROM knowledge_sections WHERE id = :i"),
            {"i": int(section_id)},
        ).rowcount
    return bool(n)


# ==================================================================
# Bucket — fichiers Markdown SOURCES du corpus ( Neon = l'original )
# ==================================================================

def put_file(path: str, subject_id: str, content: str) -> bool:
    """Stocke ( ou remplace ) un fichier .md source dans le bucket.

    Idempotent : un fichier dont le sha256 n'a pas changé n'est pas
    réécrit. Retour True si écrit, False si inchangé.
    """
    import hashlib
    import time as _time

    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    with _engine().begin() as conn:
        row = conn.execute(
            text("SELECT sha256 FROM knowledge_files WHERE path = :p"),
            {"p": path},
        ).first()
        if row is not None and row[0] == sha:
            return False
        conn.execute(
            text(
                "INSERT INTO knowledge_files "
                "(path, subject_id, content, sha256, created_at) "
                "VALUES (:p, :sid, :c, :sha, :created) "
                "ON CONFLICT (path) DO UPDATE SET "
                "subject_id = EXCLUDED.subject_id, "
                "content = EXCLUDED.content, "
                "sha256 = EXCLUDED.sha256"
            ),
            {
                "p": path,
                "sid": subject_id,
                "c": content,
                "sha": sha,
                "created": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
    return True


def list_files(subject_id: str | None = None) -> list[dict]:
    """Inventaire du bucket ( sans les contenus )."""
    sql = (
        "SELECT path, subject_id, sha256, created_at "
        "FROM knowledge_files"
    )
    params: dict[str, str] = {}
    if subject_id:
        sql += " WHERE subject_id = :sid"
        params["sid"] = subject_id
    sql += " ORDER BY path"
    with _engine().connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [
        {"path": r[0], "subject_id": r[1], "sha256": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_file(path: str) -> str | None:
    """Contenu brut d'un fichier du bucket ( None si absent )."""
    with _engine().connect() as conn:
        row = conn.execute(
            text("SELECT content FROM knowledge_files WHERE path = :p"),
            {"p": path},
        ).first()
    return row[0] if row else None


def _parse_pg_vector(value) -> list[float]:
    """pgvector → list[float].

    Selon le driver, une colonne `vector` revient tantôt en `str`
    ('[0.1,0.2]'), tantôt déjà en séquence : on gère les deux.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if not s:
        return []
    return [float(x) for x in s.split(",") if x.strip()]


def list_chunk_vectors(
    subject_id: str | None = None,
    limit: int = 2000,
) -> list[dict]:
    """Vecteurs des sections ( pour la visualisation 3D admin ).

    Retourne, borné à `limit`, [{id, subject_id, topic_slug, title,
    source_label, author, embedding}]. Les sections sans vecteur sont
    exclues (`embedding IS NOT NULL`). Jamais d'exception : la viz ne
    doit pas casser l'admin ( liste vide en cas d'erreur ).
    """
    sql = (
        "SELECT id, subject_id, topic_slug, title, source_label, author, "
        "embedding FROM knowledge_sections WHERE embedding IS NOT NULL"
    )
    params: dict = {"k": int(max(1, limit))}
    if subject_id:
        sql += " AND subject_id = :sid"
        params["sid"] = subject_id
    sql += " ORDER BY id LIMIT :k"
    with _engine().connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [
        {
            "id": r[0],
            "subject_id": r[1],
            "topic_slug": r[2],
            "title": r[3] or r[2],
            "source_label": r[4] or "",
            "author": r[5] or "",
            "embedding": _parse_pg_vector(r[6]),
        }
        for r in rows
    ]


def reconcile_subject_sources(
    subject_id: str,
    live_sources: set[str],
) -> dict:
    """Supprime les sections/fichiers dont la source n'existe plus.

    `live_sources` = ensemble des `source_label` ENCORE présents ( issus
    des fichiers réellement fournis ). Toute section du sujet absente de
    cet ensemble est supprimée, ainsi que les fichiers du bucket
    `knowledge_files` dont le `path` n'y figure pas. Un ensemble VIDE
    purge l'intégralité du sujet ( utilisé pour retirer une matière ).

    Retourne {subject_id, live_sources, deleted_sections, deleted_files}.
    Opération DESTRUCTIVE mais SCOPÉE à un seul sujet — jamais globale.
    """
    live = {str(s) for s in live_sources}
    with _engine().begin() as conn:
        if live:
            deleted_sections = conn.execute(
                text(
                    "DELETE FROM knowledge_sections "
                    "WHERE subject_id = :sid "
                    "AND NOT (source_label = ANY(:live))"
                ),
                {"sid": subject_id, "live": list(live)},
            ).rowcount
            deleted_files = conn.execute(
                text(
                    "DELETE FROM knowledge_files "
                    "WHERE subject_id = :sid "
                    "AND NOT (path = ANY(:live))"
                ),
                {"sid": subject_id, "live": list(live)},
            ).rowcount
        else:
            deleted_sections = conn.execute(
                text("DELETE FROM knowledge_sections WHERE subject_id = :sid"),
                {"sid": subject_id},
            ).rowcount
            deleted_files = conn.execute(
                text("DELETE FROM knowledge_files WHERE subject_id = :sid"),
                {"sid": subject_id},
            ).rowcount

    result = {
        "subject_id": subject_id,
        "live_sources": len(live),
        "deleted_sections": int(deleted_sections or 0),
        "deleted_files": int(deleted_files or 0),
    }
    log_event(
        "KNOWLEDGE_RECONCILE",
        message=(
            f"Réconciliation | subject={subject_id} | "
            f"supprimées={result['deleted_sections']} sections, "
            f"{result['deleted_files']} fichiers"
        ),
        extra={"operation": "knowledge_reconcile", "subject": subject_id},
    )
    return result


# ==================================================================
# Définitions de matières — YAML sources dans Neon
# ==================================================================

def upsert_subject_definition(
    subject_id: str,
    yaml_text: str,
    status: str | None = None,
    author: str | None = None,
) -> bool:
    """Stocke ( ou remplace ) un YAML de définition de matière.

    Idempotent par sha256. `status`/`author` sont OPTIONNELS : absents
    (None), le statut et l'auteur existants sont PRÉSERVÉS — un
    ré-import de contenu ne doit jamais réinitialiser la validation
    admin ( fail-closed : un nouveau sujet reste 'draft' ).
    Retour True si écrit, False si inchangé.
    """
    import hashlib
    import time as _time

    sha = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
    with _engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT sha256, status, author FROM subject_definitions "
                "WHERE subject_id = :s"
            ),
            {"s": subject_id},
        ).first()
        cur_status = row[1] if row is not None else "draft"
        cur_author = row[2] if row is not None else ""
        new_status = status if status is not None else (cur_status or "draft")
        new_author = author if author is not None else (cur_author or "")
        if (
            row is not None
            and row[0] == sha
            and new_status == cur_status
            and new_author == cur_author
        ):
            return False
        conn.execute(
            text(
                "INSERT INTO subject_definitions "
                "(subject_id, yaml, sha256, status, author, updated_at) "
                "VALUES (:s, :y, :sha, :st, :a, :u) "
                "ON CONFLICT (subject_id) DO UPDATE SET "
                "yaml = EXCLUDED.yaml, sha256 = EXCLUDED.sha256, "
                "status = EXCLUDED.status, author = EXCLUDED.author, "
                "updated_at = EXCLUDED.updated_at"
            ),
            {
                "s": subject_id,
                "y": yaml_text,
                "sha": sha,
                "st": new_status,
                "a": new_author,
                "u": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
    return True


def set_subject_status(
    subject_id: str, status: str, author: str | None = None
) -> bool:
    """Change le statut de validation ( + auteur optionnel ) d'une matière.

    Retour True si une ligne a été mise à jour. Le gating ( sujet non
    validé = invisible de l'agent ) est appliqué en aval par le registry.
    """
    with _engine().begin() as conn:
        if author is None:
            n = conn.execute(
                text(
                    "UPDATE subject_definitions SET status = :st "
                    "WHERE subject_id = :s"
                ),
                {"st": status, "s": subject_id},
            ).rowcount
        else:
            n = conn.execute(
                text(
                    "UPDATE subject_definitions SET status = :st, author = :a "
                    "WHERE subject_id = :s"
                ),
                {"st": status, "a": author, "s": subject_id},
            ).rowcount
    return bool(n)


def load_subject_definitions(only_validated: bool = True) -> dict[str, str]:
    """YAML des matières : {subject_id: yaml_text}.

    `only_validated=True` ( défaut, fail-closed ) ne retourne QUE les
    matières `status='validated'` — c'est le contrat consommé par le
    registry : un sujet non validé n'est jamais servi à l'agent.
    L'admin passe `only_validated=False` pour voir tout le catalogue.
    """
    sql = "SELECT subject_id, yaml FROM subject_definitions"
    if only_validated:
        sql += " WHERE status = 'validated'"
    sql += " ORDER BY 1"
    with _engine().connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return {r[0]: r[1] for r in rows}


def load_subject_meta() -> list[dict]:
    """Métadonnées de TOUTES les matières ( admin ) — sans le YAML.

    Retourne [{subject_id, status, author, sha256, updated_at}] trié par
    identifiant. Sert la liste admin ( qui affiche le statut/auteur ).
    """
    with _engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT subject_id, status, author, sha256, updated_at "
                "FROM subject_definitions ORDER BY 1"
            )
        ).fetchall()
    return [
        {
            "subject_id": r[0],
            "status": r[1] or "draft",
            "author": r[2] or "",
            "sha256": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


def get_subject_status(subject_id: str) -> str | None:
    """Statut de validation d'une matière, ou None si la matière est absente.

    Distinct de `is_subject_validated` : permet de distinguer « pas de
    matière » ( None ) de « matière non validée » ( "draft"… ) — utile
    au garde-fou du retriever ( ne pas bloquer un corpus hors registry ).
    """
    if not subject_id:
        return None
    with _engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT status FROM subject_definitions WHERE subject_id = :s"
            ),
            {"s": subject_id},
        ).first()
    return (row[0] or "draft") if row else None


def is_subject_validated(subject_id: str) -> bool:
    """Le sujet est-il validé ( status='validated' ) ? Fail-closed."""
    return get_subject_status(subject_id) == "validated"


# ==================================================================
# Propositions de connaissance — soumises par l'agent, décidées admin
# ==================================================================

PROPOSAL_STATUSES = ("pending", "approved", "rejected")

_PROPOSAL_COLUMNS = (
    "id, subject_id, title, content, author, proposed_by, reason, "
    "status, created_at, decided_at, decided_by"
)


def _proposal_row_to_dict(r) -> dict:
    return {
        "id": int(r[0]),
        "subject_id": r[1],
        "title": r[2],
        "content": r[3] or "",
        "author": r[4] or "",
        "proposed_by": r[5] or "",
        "reason": r[6] or "",
        "status": r[7] or "pending",
        "created_at": r[8] or "",
        "decided_at": r[9] or "",
        "decided_by": r[10] or "",
    }


def create_proposal(
    subject_id: str,
    title: str,
    content: str,
    author: str = "",
    proposed_by: str = "",
    reason: str = "",
) -> dict:
    """Enregistre une PROPOSITION de connaissance ( status='pending' ).

    La proposition N'EST PAS ajoutée au corpus ( elle n'est donc jamais
    retournée par la recherche ) tant qu'un admin ne l'a pas approuvée
    via `decide_proposal`. Retourne {id, subject_id, title, status}.
    """
    import time as _time

    if not (subject_id or "").strip() or not (title or "").strip():
        raise ValueError("subject_id et title sont requis")
    if not (content or "").strip():
        raise ValueError("Le contenu de la proposition est vide")

    with _engine().begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO knowledge_proposals "
                "(subject_id, title, content, author, proposed_by, reason, "
                " status, created_at) "
                "VALUES (:sid, :t, :c, :a, :pb, :r, 'pending', :created) "
                "RETURNING id"
            ),
            {
                "sid": subject_id.strip(),
                "t": title.strip(),
                "c": content.strip(),
                "a": author or "",
                "pb": proposed_by or "",
                "r": reason or "",
                "created": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        ).scalar_one()

    log_event(
        "KNOWLEDGE_PROPOSAL_CREATED",
        message=f"Proposition | {subject_id}/{title}",
        extra={
            "operation": "knowledge_proposal",
            "subject": subject_id,
            "proposal_id": int(row),
        },
    )
    return {
        "id": int(row),
        "subject_id": subject_id.strip(),
        "title": title.strip(),
        "status": "pending",
    }


def list_proposals(status: str | None = None) -> list[dict]:
    """Liste les propositions ( toutes, ou filtrées par statut )."""
    sql = f"SELECT {_PROPOSAL_COLUMNS} FROM knowledge_proposals"
    params: dict = {}
    if status:
        sql += " WHERE status = :st"
        params["st"] = status
    sql += " ORDER BY id DESC"
    with _engine().connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [_proposal_row_to_dict(r) for r in rows]


def get_proposal(proposal_id: int) -> dict | None:
    """UNE proposition par id ( None si absente )."""
    with _engine().connect() as conn:
        row = conn.execute(
            text(
                f"SELECT {_PROPOSAL_COLUMNS} FROM knowledge_proposals "
                "WHERE id = :i"
            ),
            {"i": int(proposal_id)},
        ).first()
    return _proposal_row_to_dict(row) if row else None


def decide_proposal(
    proposal_id: int, approve: bool, decided_by: str = ""
) -> dict:
    """Approuve ou rejette une proposition ( admin ).

    APPROUVER → vectorise et insère la section dans `knowledge_sections`
    ( upsert par titre ), PUIS passe la proposition à 'approved'. Si
    l'embedding échoue, la proposition RESTE 'pending' ( on n'arbitre
    jamais une proposition qu'on n'a pas pu indexer ).

    Retourne {ok, id, status, section_id}. ok=False si la proposition
    est absente ou déjà décidée.
    """
    import time as _time

    prop = get_proposal(proposal_id)
    if prop is None:
        return {"ok": False, "error": "not_found", "id": int(proposal_id)}
    if prop["status"] != "pending":
        return {
            "ok": False,
            "error": "already_decided",
            "id": int(proposal_id),
            "status": prop["status"],
        }

    section_id: int | None = None
    if approve:
        try:
            result = upsert_section(
                subject_id=prop["subject_id"],
                title=prop["title"],
                content=prop["content"],
                source_label=f"proposal/{proposal_id}",
                author=prop["author"],
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": "embedding_failed",
                "detail": str(exc),
                "id": int(proposal_id),
            }
        section_id = result["id"]

    new_status = "approved" if approve else "rejected"
    with _engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE knowledge_proposals "
                "SET status = :st, decided_at = :d, decided_by = :by "
                "WHERE id = :i"
            ),
            {
                "st": new_status,
                "d": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                "by": decided_by or "",
                "i": int(proposal_id),
            },
        )

    log_event(
        "KNOWLEDGE_PROPOSAL_DECIDED",
        message=f"Proposition {proposal_id} → {new_status}",
        extra={
            "operation": "knowledge_proposal_decide",
            "proposal_id": int(proposal_id),
            "status": new_status,
        },
    )
    return {
        "ok": True,
        "id": int(proposal_id),
        "status": new_status,
        "section_id": section_id,
    }


def delete_proposal(proposal_id: int) -> bool:
    """Supprime une proposition ( admin ). True si supprimée."""
    with _engine().begin() as conn:
        n = conn.execute(
            text("DELETE FROM knowledge_proposals WHERE id = :i"),
            {"i": int(proposal_id)},
        ).rowcount
    return bool(n)


def _slugify(text_value: str) -> str:
    """Slug accent-less minuscule — cohérent avec le découpage
    d'indexation ( sections « ## Titre » → slug )."""
    import re
    import unicodedata

    normalized = "".join(
        c
        for c in unicodedata.normalize("NFKD", text_value or "")
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", normalized).strip().lower()


__all__ = [
    "has_subject_corpus",
    "list_topics",
    "get_section",
    "match_section",
    "search_semantic",
    "search_hybrid",
    "upsert_section",
    "list_sections",
    "delete_section",
    "put_file",
    "list_files",
    "get_file",
    "list_chunk_vectors",
    "reconcile_subject_sources",
    "upsert_subject_definition",
    "load_subject_definitions",
    "load_subject_meta",
    "set_subject_status",
    "get_subject_status",
    "is_subject_validated",
    "create_proposal",
    "list_proposals",
    "get_proposal",
    "decide_proposal",
    "delete_proposal",
    "PROPOSAL_STATUSES",
    "min_score",
]
