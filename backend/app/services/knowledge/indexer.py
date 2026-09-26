# Indexation du corpus knowledge → Neon ( knowledge_sections ).
#
# Le dossier backend/app/knowledge ( ~70 Markdown ) reste la SOURCE DE
# VÉRITÉ ; Neon est un CACHE indexé. L'indexation est IDEMPOTENTE : un
# fichier n'est ré-embeddé que si son sha256 a changé. Au démarrage,
# seules les différences coûtent un appel au provider d'embeddings.
#
# Découpage en sections : REPREND _split_sections de knowledge_retriever
# ( découpe sur les titres `##` ) — indexer et rechercher doivent VOIR
# EXACTEMENT les mêmes sections, sinon le cache et le disque divergent.
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.logging.events import log_event

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _split_sections(content: str) -> list[tuple[str, str, str]]:
    """Découpe un .md en sections.

    Retour [(topic_slug, title_brut, contenu)] — le topic est le slug
    accent-less ( clé de recherche ), le title est le libellé d'origine
    ( affiché ). Cohérent avec knowledge_retriever._split_sections.
    """
    sections: list[tuple[str, str, str]] = []
    current_topic = "_intro"
    current_title = "(introduction)"
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                sections.append(
                    (
                        current_topic,
                        current_title,
                        "\n".join(current_lines).strip(),
                    )
                )
            current_title = m.group(1).strip()
            current_topic = _strip_accents(current_title.lower())
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            (current_topic, current_title, "\n".join(current_lines).strip())
        )
    return [(t, ti, c) for t, ti, c in sections if c]


def _h1(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _embeddings_client():
    """Provider d'embeddings actif ( embeddings.yaml ).

    API : provider.embed_text(str) -> list[float]. JAMAIS de fallback
    silencieux : si le provider ne répond pas, on propage — mieux vaut
    une table vide qu'un index sans vecteurs.
    """
    from app.services.context.semantic.provider import get_embedding_provider

    return get_embedding_provider()


def _conn():
    from app.infrastructure.database.persistence import _postgres_url

    from sqlalchemy import create_engine

    return create_engine(_postgres_url(), pool_pre_ping=True)


def _existing_shas(conn, subject_id: str) -> dict[tuple[str, str], str]:
    """( subject_id, topic_slug ) -> source_sha déjà indexés ( lecture seule )."""
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT subject_id, topic_slug, source_sha "
            "FROM knowledge_sections WHERE subject_id = :sid"
        ),
        {"sid": subject_id},
    ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def index_corpus(force: bool = False) -> dict:
    """Indexe ( ou ré-indexe les changements ) du corpus knowledge.

    Args:
        force: ré-embedder même les sections inchangées ( changement
               de modèle d'embeddings, par exemple ).

    Retourne {files, sections, embedded, skipped, deleted, errors}.
    """
    if not KNOWLEDGE_DIR.exists():
        log_event(
            "KNOWLEDGE_INDEX_EMPTY",
            level="WARNING",
            message=f"{KNOWLEDGE_DIR} introuvable — rien à indexer",
        )
        return {"files": 0, "sections": 0, "embedded": 0, "skipped": 0,
                "deleted": 0, "errors": []}

    stats = {
        "files": 0, "sections": 0, "embedded": 0, "skipped": 0,
        "deleted": 0, "errors": [],
    }
    client = _embeddings_client()

    files = sorted(KNOWLEDGE_DIR.rglob("*.md"))
    stats["files"] = len(files)

    seen: set[tuple[str, str]] = set()
    batch_meta: list[tuple[str, str, str, str, str, str]] = []
    # ( subject_id, topic_slug, title, content, source_sha, source_label )

    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            stats["errors"].append(f"{path}: {exc}")
            continue
        if not content.strip():
            continue

        # subject_id = première composante du chemin ( informatique,
        # mathematics… ) ; topic = sous-dossier ou README du sujet.
        rel = path.relative_to(KNOWLEDGE_DIR)
        parts = rel.parts
        subject_id = parts[0]
        sha = _sha256(content)
        h1 = _h1(content) or subject_id

        for topic_slug, title, body in _split_sections(content):
            key = (subject_id, topic_slug)
            seen.add(key)
            stats["sections"] += 1
            batch_meta.append(
                (subject_id, topic_slug, title, body, sha,
                 f"{rel.parent.name}/{rel.stem}")
            )

    # Supprime les sections dont le fichier a disparu ou a changé de
    # structure. Idempotence : la base reflète EXACTEMENT le disque.
    engine = _conn()
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            existing_sha_rows = conn.execute(
                text("SELECT subject_id, topic_slug, source_sha FROM knowledge_sections")
            ).fetchall()
        existing_map: dict[tuple[str, str], str] = {
            (r[0], r[1]): r[2] for r in existing_sha_rows
        }

        to_embed: list[tuple[int, tuple]] = []
        for i, (sid, topic, title, body, sha, label) in enumerate(batch_meta):
            key = (sid, topic)
            if not force and existing_map.get(key) == sha:
                stats["skipped"] += 1
                continue
            to_embed.append((i, (sid, topic, title, body, sha, label)))

        if to_embed:
            # provider.embed_text est unitaire ( pas de batch ) — on
            # boucle. Un provider KO → échec EXPLICITE, pas de fallback.
            vectors: list[list[float]] = []
            try:
                for _i, meta in to_embed:
                    sid, topic, title, body, sha, label = meta
                    vectors.append(
                        client.embed_text(f"{title}\n{body[:4000]}")
                    )
            except Exception as exc:
                stats["errors"].append(f"embeddings provider: {exc}")
                log_event(
                    "KNOWLEDGE_EMBED_FAILED",
                    level="ERROR",
                    message=(
                        f"Provider d'embeddings KO — {len(to_embed)} sections "
                        f"non indexées : {exc}"
                    ),
                )
                return stats

            with engine.begin() as conn:
                for (i, meta), vec in zip(to_embed, vectors):
                    sid, topic, title, body, sha, label = meta
                    conn.execute(
                        text(
                            "INSERT INTO knowledge_sections "
                            "(subject_id, topic_slug, title, content, "
                            " source_sha, source_label, embedding) "
                            "VALUES (:sid, :topic, :title, :content, "
                            "        :sha, :label, CAST(:vec AS vector)) "
                            "ON CONFLICT (subject_id, topic_slug) DO UPDATE SET "
                            "  title = :title, content = :content, "
                            "  source_sha = :sha, source_label = :label, "
                            "  embedding = CAST(:vec AS vector)"
                        ),
                        {
                            "sid": sid, "topic": topic, "title": title,
                            "content": body, "sha": sha, "label": label,
                            "vec": _vec_literal(vec),
                        },
                    )
                stats["embedded"] = len(to_embed)

        # Suppression des sections obsolètes ( fichier disparu ).
        with engine.begin() as conn:
            if seen:
                # Supprime tout ce qui n'est plus dans le corpus.
                rows = conn.execute(
                    text("SELECT subject_id, topic_slug FROM knowledge_sections")
                ).fetchall()
                stale = [(r[0], r[1]) for r in rows if (r[0], r[1]) not in seen]
                for sid, topic in stale:
                    conn.execute(
                        text(
                            "DELETE FROM knowledge_sections "
                            "WHERE subject_id = :sid AND topic_slug = :topic"
                        ),
                        {"sid": sid, "topic": topic},
                    )
                stats["deleted"] = len(stale)
    finally:
        engine.dispose()

    log_event(
        "KNOWLEDGE_INDEXED",
        message=(
            f"Corpus indexé | files={stats['files']} "
            f"sections={stats['sections']} embedded={stats['embedded']} "
            f"skipped={stats['skipped']} deleted={stats['deleted']} "
            f"errors={len(stats['errors'])}"
        ),
    )
    return stats


def _vec_literal(vec) -> str:
    """Vecteur → litéral pgvector '[0.1,0.2,…]'."""
    try:
        nums = list(vec)
    except TypeError:
        return "[]"
    return "[" + ",".join(repr(float(x)) for x in nums) + "]"


__all__ = ["index_corpus", "KNOWLEDGE_DIR"]
