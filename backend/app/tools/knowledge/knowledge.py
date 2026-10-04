# Tool search_knowledge — recherche EXPLICITE dans le corpus de cours.
#
# La voie PAR DÉFAUT vers le corpus reste l'injection automatique du
# context builder ( knowledge_retriever appelé sans le modèle ). Ce tool
# donne au LLM une voie EXPLICITE et auditable : il décide quand relancer
# une recherche ciblée dans une matière. Il ne sert QUE les matières
# validées ( gating appliqué par knowledge_retriever.search_knowledge ).
#
# FAIL-SAFE : jamais d'exception propagée — une erreur devient un statut
# contrôlé, comme les autres tools.
from __future__ import annotations

import json

from langchain_core.tools import tool

from app.logging.events import log_event


@tool
def search_knowledge(
    subject: str,
    query: str,
    top_k: int = 3,
) -> str:
    """Recherche des extraits pertinents dans la BASE DE CONNAISSANCE
    des cours ( corpus validé ) pour une matière donnée.

    Renvoie un JSON {status, query, results:[{title, source, content,
    relevance, author}]}. status ∈ found / insufficient / unavailable /
    error. Cite les extraits retournés dans ta réponse ; ne les invente
    jamais. `subject` doit être l'identifiant d'une matière (ex:
    "python") ; une matière non validée par l'admin renvoie unavailable.

    À utiliser quand une recherche ciblée dans le cours est nécessaire
    (préciser un point, retrouver une définition) plutôt que de te fier
    au seul contexte déjà présent.
    """
    from app.services.context.knowledge_retriever import (
        search_knowledge as _search,
    )

    q = (query or "").strip()
    subj = (subject or "").strip()
    log_event(
        "TOOL_CALL",
        message=f"search_knowledge subject={subj} query={q[:80]}",
        tool_name="search_knowledge",
    )
    if not q or not subj:
        return json.dumps(
            {"status": "unavailable", "query": q, "results": []},
            ensure_ascii=False,
        )
    try:
        resp = _search(
            subject_id=subj,
            query=q,
            limit=max(1, min(int(top_k), 10)),
        )
    except Exception as exc:  # noqa: BLE001 — fail-safe §15
        return json.dumps(
            {"status": "error", "query": q, "error": str(exc), "results": []},
            ensure_ascii=False,
        )

    results = [
        {
            "title": r.get("title", ""),
            "source": r.get("source", ""),
            "content": r.get("content", ""),
            "relevance": r.get("relevance", 0.0),
            "author": (r.get("metadata") or {}).get("author", ""),
        }
        for r in resp.get("results", [])
    ]
    return json.dumps(
        {
            "status": resp.get("status", "unavailable"),
            "query": resp.get("query", q),
            "subject": subj,
            "results": results,
        },
        ensure_ascii=False,
    )


@tool
def propose_knowledge(
    subject: str,
    title: str,
    content: str,
    reason: str = "",
) -> str:
    """Propose d'AJOUTER une connaissance au corpus d'une matière.

    La proposition est enregistrée puis soumise à l'APPROBATION d'un
    ADMIN : elle n'est PAS disponible à la recherche tant que l'admin ne
    l'a pas approuvée. À utiliser quand l'agent identifie un complément de
    cours fiable et manquant (définition, exemple, précision) — jamais
    pour du contenu inventé ou hors sujet.

    Args:
        subject: identifiant de la matière cible (ex: "python").
        title: titre court de la section proposée.
        content: contenu complet (Markdown) de la proposition.
        reason: pourquoi cette connaissance est un complément utile.

    Renvoie un JSON {status, proposal_id, subject, message}. status ∈
    proposed / rejected / error.
    """
    from app.services.knowledge import store

    subj = (subject or "").strip()
    log_event(
        "TOOL_CALL",
        message=f"propose_knowledge subject={subj}",
        tool_name="propose_knowledge",
    )
    if not subj or not (title or "").strip() or not (content or "").strip():
        return json.dumps(
            {
                "status": "rejected",
                "message": "subject, title et content sont requis.",
            },
            ensure_ascii=False,
        )
    try:
        # Une proposition ne vise qu'une matière CONNUE ( toute de statut ) :
        # proposer vers une matière inexistante créerait du bruit que
        # l'admin ne peut rattacher à rien.
        if store.get_subject_status(subj) is None:
            return json.dumps(
                {
                    "status": "rejected",
                    "message": f"Matière inconnue : {subj}.",
                },
                ensure_ascii=False,
            )
        result = store.create_proposal(
            subject_id=subj,
            title=title,
            content=content,
            reason=reason,
        )
    except Exception as exc:  # noqa: BLE001 — fail-safe §15
        return json.dumps(
            {"status": "error", "message": str(exc)}, ensure_ascii=False
        )
    return json.dumps(
        {
            "status": "proposed",
            "proposal_id": result["id"],
            "subject": result["subject_id"],
            "message": (
                "Proposition enregistrée — un administrateur doit "
                "l'approuver avant qu'elle ne rejoigne le corpus."
            ),
        },
        ensure_ascii=False,
    )


knowledge_tools = [search_knowledge, propose_knowledge]

__all__ = ["search_knowledge", "propose_knowledge", "knowledge_tools"]
