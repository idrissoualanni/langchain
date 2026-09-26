"""Repository du contrôle d'accès knowledge (façade de ``resolver``)."""
from __future__ import annotations

from typing import Literal

from app.services.knowledge import resolver as _resolver_service


def register_knowledge_base(
    info: _resolver_service.KnowledgeBaseInfo,
) -> None:
    """Enregistre une base de connaissance dans le registre."""
    _resolver_service.register_knowledge_base(info)


def get_knowledge_base(
    kb_id: str,
) -> _resolver_service.KnowledgeBaseInfo | None:
    """Retourne les informations d'une base de connaissance."""
    return _resolver_service.get_knowledge_base(kb_id)


def list_knowledge_bases() -> list[_resolver_service.KnowledgeBaseInfo]:
    """Liste toutes les bases de connaissance enregistrées."""
    return _resolver_service.list_knowledge_bases()


def add_access_rule(rule: _resolver_service.KnowledgeAccessRule) -> None:
    """Ajoute une règle d'accès pour une base de connaissance."""
    _resolver_service.add_access_rule(rule)


def remove_access_rule(rule: _resolver_service.KnowledgeAccessRule) -> bool:
    """Supprime une règle d'accès (False si elle n'existe pas)."""
    return _resolver_service.remove_access_rule(rule)


def check_access(
    knowledge_base_id: str,
    user_id: str,
    group_ids: list[str] | None = None,
    is_admin: bool = False,
) -> _resolver_service.AccessResult:
    """Vérifie si un utilisateur peut accéder à une base donnée."""
    return _resolver_service.check_access(
        knowledge_base_id, user_id, group_ids, is_admin
    )


def get_accessible_knowledge_bases(
    user_id: str,
    group_ids: list[str] | None = None,
    is_admin: bool = False,
) -> list[str]:
    """Liste les bases de connaissance accessibles à un utilisateur."""
    return _resolver_service.get_accessible_knowledge_bases(
        user_id, group_ids, is_admin
    )


def grant_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Accorde un accès à une base de connaissance."""
    return _resolver_service.grant_access(
        knowledge_base_id, scope, target_id
    )


def revoke_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Révoque un accès à une base de connaissance."""
    return _resolver_service.revoke_access(
        knowledge_base_id, scope, target_id
    )


def clear_all_rules() -> None:
    """Supprime toutes les règles d'accès (contexte de test)."""
    _resolver_service.clear_all_rules()


def clear_rules_for_kb(kb_id: str) -> int:
    """Supprime les règles d'une seule base (nombre supprimé)."""
    return _resolver_service.clear_rules_for_kb(kb_id)


def list_rules_for_kb(
    kb_id: str,
) -> list[_resolver_service.KnowledgeAccessRule]:
    """Liste les règles d'accès d'une seule base de connaissance."""
    return _resolver_service.list_rules_for_kb(kb_id)


def unregister_knowledge_base(kb_id: str) -> bool:
    """Retire une base du registre (False si elle n'existe pas)."""
    return _resolver_service.unregister_knowledge_base(kb_id)


def clear_all_knowledge_bases() -> None:
    """Supprime toutes les bases enregistrées (contexte de test)."""
    _resolver_service.clear_all_knowledge_bases()


# ------------------------------------------------------------------
# Recherche sémantique dans knowledge_sections ( pgvector )
# ------------------------------------------------------------------
# Le corpus indexé par app.services.knowledge.indexer est stocké avec
# son embedding. La recherche se fait DANS la base ( ORDER BY
# embedding <=> :q ) plutôt qu'en Python : pgvector fait le calcul
# côté serveur, ce qui évite de rapatrier 545 vecteurs de 1024 dims.


def semantic_search(
    query: str,
    top_k: int = 6,
    subject_id: str | None = None,
) -> list[dict]:
    """Recherche les sections knowledge les plus proches de ``query``.

    Args:
        query: texte de la question ( embeddé puis comparé ).
        top_k: nombre maximum de sections retournées.
        subject_id: restreint à une matière ( None = tout le corpus ).

    Returns:
        Liste de dicts { subject_id, topic_slug, title, content, score }
        triés par similarité décroissante. Liste vide si erreur ( fail-safe
        — la recherche sémantique ne doit jamais casser le pipeline ).
    """
    from sqlalchemy import text

    from app.infrastructure.database.connections import get_conn
    from app.services.context.semantic.provider import get_embedding_provider

    try:
        vec = get_embedding_provider().embed_text(query or "")
        vec_literal = ",".join(f"{x:.10f}" for x in vec)
        clauses = ["embedding IS NOT NULL"]
        params: dict[str, object] = {"q": f"[{vec_literal}]", "k": top_k}
        if subject_id:
            clauses.append("subject_id = :sid")
            params["sid"] = subject_id
        where = " AND ".join(clauses)
        conn = get_conn()
        rows = conn.execute(
            text(
                "SELECT subject_id, topic_slug, title, content, "
                "       (embedding <=> CAST(:q AS vector)) AS distance "
                f"FROM knowledge_sections WHERE {where} "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT :k"
            ),
            params,
        ).fetchall()
        results = []
        for r in rows:
            distance = float(r[4]) if r[4] is not None else 1.0
            # distance cosine 0 (identique) → 2 (opposé) ; on normalise
            # en score de similarité [0..1] pour rester comparable aux
            # autres scores du pipeline sémantique.
            score = max(0.0, 1.0 - (distance / 2.0))
            results.append(
                {
                    "subject_id": r[0],
                    "topic_slug": r[1],
                    "title": r[2],
                    "content": r[3],
                    "score": round(score, 4),
                }
            )
        return results
    except Exception as exc:  # noqa: BLE001 — fail-safe §15/§19
        from app.logging.events import log_event

        log_event(
            "KNOWLEDGE_SEARCH_ERROR",
            level="ERROR",
            message=f"Recherche sémantique knowledge KO : {exc}",
        )
        return []


__all__ = [
    "register_knowledge_base",
    "get_knowledge_base",
    "list_knowledge_bases",
    "add_access_rule",
    "remove_access_rule",
    "check_access",
    "get_accessible_knowledge_bases",
    "grant_access",
    "revoke_access",
    "clear_all_rules",
    "clear_rules_for_kb",
    "list_rules_for_kb",
    "unregister_knowledge_base",
    "clear_all_knowledge_bases",
    "semantic_search",
]
