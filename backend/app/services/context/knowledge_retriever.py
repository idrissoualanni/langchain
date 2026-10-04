# Knowledge Retriever — QUOI enseigner. Neon pgvector = SEULE source.
#
# Le corpus vivait en fichiers Markdown ( backend/app/knowledge/ ) :
# il vit DÉSORMAIS dans Neon ( knowledge_sections, vectorisé
# qwen3-embedding:0.6b ) — mission « aucune base de connaissance
# codée en dur dans le projet ». Ce module conserve le CONTRAT
# public V6.5 ( dict SearchResponse-compatible, consommé par le
# builder, learning_context, learning_profile et les tests ) et
# délègue la recherche vectorielle au store Neon.
#
# Formule lexicale §42-C retirée avec les fichiers : la pertinence
# est désormais la similarité cosinus du provider actif ( cohérence
# index ↔ requête garantie par embeddings.yaml ).
from __future__ import annotations

from app.services.context.query_norm import normalize_query
from app.services.knowledge import store
from app.services.knowledge.rerank import rerank
from app.schemas.context import SearchResult
from app.logging.events import log_event

# Status possibles (§16) : found / insufficient / unavailable
# (+ "error" transporté par SearchResponse V6.5)
STATUS_FOUND = "found"
STATUS_INSUFFICIENT = "insufficient"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


def search_knowledge(
    subject_id: str,
    topic: str | None = None,
    query: str = "",
    limit: int = 3,
    user_id: str | None = None,
    is_admin: bool = False,
) -> dict:
    """Recherche les sections knowledge pertinentes (V6.5).

    Pipeline : requête ( topic de repli ) → embedding par le provider
    actif → cosine pgvector dans knowledge_sections ( sujet filtré )
    → seuil → top_k (limit). Neon est la seule source : pas de repli
    fichier.

    ACL ( §11-§18 ) : si une knowledge base d'id = subject_id est
    enregistrée ( admin ), l'accès de l'utilisateur est vérifié
    ( règles user/group/public persistées dans Neon ) — refus =
    unavailable, jamais de fuite de contenu. Sans KB enregistrée le
    corpus reste ouvert ( rétro-compatibilité ).

    Retourne un dict SearchResponse-compatible :
    {
        "status": found|insufficient|unavailable,
        "query": <requête normalisée>,
        "results": [SearchResult.model_dump()...],
        "items": [compat V5 builder],
        "searched_sources": <sections candidats du sujet>,
    }
    """
    q_norm = normalize_query(query or (topic or ""))

    # ---- ACL : une KB d'id = subject_id restreint le corpus ----
    try:
        from app.services.knowledge.resolver import (
            check_access,
            is_corpus_restricted,
        )

        if user_id and is_corpus_restricted(subject_id):
            access = check_access(subject_id, user_id, None, is_admin)
            if not access.allowed:
                log_event(
                    "KNOWLEDGE_ACCESS_DENIED",
                    level="WARNING",
                    message=(
                        f"Corpus {subject_id} refusé à {user_id} "
                        f"({access.reason})"
                    ),
                    extra={
                        "operation": "knowledge_search",
                        "subject": subject_id,
                        "status": STATUS_UNAVAILABLE,
                        "items": 0,
                    },
                )
                return {
                    "status": STATUS_UNAVAILABLE,
                    "query": q_norm,
                    "results": [],
                    "items": [],
                    "searched_sources": 0,
                }
    except Exception:  # noqa: BLE001 — l'ACL ne doit jamais casser la
        pass  # recherche ( fail-safe : tables absentes, DB down… )

    # ---- Gating validation admin ( ceinture + bretelles §17 ) ----
    # Le registry exclut déjà les matières non validées ; on revérifie
    # ici car search_knowledge peut être appelé avec un subject_id direct
    # ( tool, admin ). Seul un statut EXISTANT et ≠ 'validated' bloque —
    # une matière absente ( None ) n'est pas bloquée par ce garde-fou
    # ( corpus hors registry, tests ). Fail-safe : toute erreur DB est
    # ignorée pour ne jamais casser la recherche.
    try:
        status = store.get_subject_status(subject_id)
        if status is not None and status != "validated":
            log_event(
                "KNOWLEDGE_SUBJECT_NOT_VALIDATED",
                level="WARNING",
                message=(
                    f"Corpus {subject_id} non validé (status={status}) — "
                    "recherche refusée"
                ),
                extra={
                    "operation": "knowledge_search",
                    "subject": subject_id,
                    "status": STATUS_UNAVAILABLE,
                },
            )
            return {
                "status": STATUS_UNAVAILABLE,
                "query": q_norm,
                "results": [],
                "items": [],
                "searched_sources": 0,
            }
    except Exception:  # noqa: BLE001
        pass

    try:
        # 1. Génération d'un POOL de candidates ( hybride HNSW + tsvector )
        #    plus large que le top demandé — le reranking a besoin de marge.
        query_text = query or (topic or "")
        candidates = store.search_hybrid(
            subject_id, query_text, limit=max(limit * 4, 8)
        )
        # 2. RERANKING ( signaux lexicaux fins ) → top_k final.
        hits = rerank(query_text, candidates, top_k=limit)
        has_corpus = store.has_subject_corpus(subject_id)
    except Exception as exc:
        # Base injoignable : unavailable explicite ( jamais un
        # repli silencieux qui masquerait une config cassée ).
        log_event(
            "KNOWLEDGE_SEARCH",
            level="WARNING",
            message=f"Knowledge store injoignable: {exc}",
            extra={
                "operation": "knowledge_search",
                "subject": subject_id,
                "topic": topic or "",
                "status": STATUS_UNAVAILABLE,
                "items": 0,
            },
        )
        return {
            "status": STATUS_UNAVAILABLE,
            "query": q_norm,
            "results": [],
            "items": [],
            "searched_sources": 0,
        }

    items: list[SearchResult] = [
        SearchResult(
            title=h["title"],
            source=h["source"],
            content=h["content"],
            relevance=h["relevance"],
            source_type="local_knowledge",
            metadata={
                "section": h["topic"],
                "author": h.get("author", ""),
            },
        )
        for h in hits
    ]

    status = (
        STATUS_UNAVAILABLE
        if not has_corpus
        else (STATUS_FOUND if items else STATUS_INSUFFICIENT)
    )

    # Compat V5 : vue items pour le builder
    legacy_items = [
        {
            "source": r.source,
            "topic": r.metadata.get("section", ""),
            "content": r.content,
            "relevance": r.relevance,
        }
        for r in items
    ]

    log_event(
        "KNOWLEDGE_SEARCH",
        message=(
            f"Knowledge search | subject={subject_id} | "
            f"topic={topic} | status={status} | items={len(items)}"
        ),
        extra={
            "operation": "knowledge_search",
            "subject": subject_id,
            "topic": topic or "",
            "status": status,
            "items": len(items),
        },
    )
    return {
        "status": status,
        "query": q_norm,
        "results": [r.model_dump() for r in items],
        "items": legacy_items,
        "searched_sources": len(legacy_items),
    }


__all__ = ["search_knowledge", "STATUS_FOUND", "STATUS_INSUFFICIENT", "STATUS_UNAVAILABLE", "STATUS_ERROR"]
