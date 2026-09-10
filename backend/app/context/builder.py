# Context Builder V4 — assemble le contexte dynamique multi-sources.
# Séparation des responsabilités (§42) :
#   Router         → de quoi parle la question
#   Registry       → config de la matière
#   Retriever      → connaissances pertinentes
#   Tool Registry  → actions disponibles
#   User Memory    → durable user
#   Thread State   → conversation courante
#   Builder        = SÉLECTIONNE (ce module)
#   Prompt Builder = ASSEMBLE
from app.logging.events import log_event

from app.context.knowledge_retriever import search_knowledge
from app.context.router import route_subject
from app.context.thread_context import build_thread_context
from app.context.tool_context import build_tool_context
from app.context.user_context import build_user_context
from app.subjects.registry import get_subject

__all__ = [
    "build_context",
    "build_user_context",
    "build_thread_context",
    "build_system_prompt",
    "route_subject",
]

from app.context.prompt_builder import build_system_prompt

from app.agent.memory import (
    list_facts,
    read_profile,
    search_facts,
)


def _select_memories(
    user_id: str, query: str, max_memories: int
) -> list[dict]:
    """Sélection mémoire V4 (fix §39) :

    1. Search par pertinence query (comme V3).
    2. Fill récent SEULEMENT si la search n'a rien retourné,
       plafonné à 3 faits (identity + 2 plus récents) — jamais
       "toute la mémoire" (§22 pertinence + §39 qualité).
    """
    relevant: list[dict] = []
    if query and query.strip():
        try:
            relevant = search_facts(
                user_id, query, limit=max_memories
            )
        except Exception:
            relevant = []

    if not relevant:
        # Fill minimal : 1 fait identity/background + 2 plus récents
        try:
            all_facts = list_facts(user_id)
        except Exception:
            all_facts = []
        if all_facts:
            core_cats = [
                f
                for f in all_facts
                if f.get("category") in ("identity", "background")
            ]
            others = [
                f
                for f in all_facts
                if f.get("category")
                not in ("identity", "background")
            ]
            fill = core_cats[:1] + list(reversed(others))[:2]
            seen: set[str] = set()
            relevant = []
            for f in fill:
                fid = f.get("id")
                if fid not in seen:
                    seen.add(fid)
                    relevant.append(f)
    return relevant


def build_context(
    user_id: str,
    thread_id: str,
    query: str,
    subject: str | None = None,
    topic: str | None = None,
    max_memories: int = 12,
    max_knowledge: int = 3,
) -> dict:
    """Construit le contexte complet d'un appel LLM (V4 multi-sources).

    Retourne :
    {
        "router":    {subject, topic, confidence, status, candidates, subjects},
        "subject":   config matière (dict) ou None,
        "knowledge": {"status", "items", "searched_sources"},
        "tools":     {"available", "declared_common", "declared_specialized", ...},
        "user":      {"text", "facts_count"},
        "thread":    {"thread_id", "message_count", "text"},
        "learning":  None (réservé Learning Profile V5+),
        "relevant_memories": [...],
        "stats":     observabilité,
    }

    Émet CONTEXT_BUILD_START / CONTEXT_BUILD_END + SELECTED_* par source.
    """
    log_event(
        "CONTEXT_BUILD_START",
        message=(
            f"Context build start | user={user_id} | "
            f"thread={thread_id}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "context_build",
            "query": (query or "")[:100],
        },
    )

    # --- 1. ROUTING ---
    routing = route_subject(query, hint_subject=subject)

    # --- 2. SUBJECT CONFIG ---
    subject_cfg = (
        get_subject(routing.subject) if routing.subject else None
    )
    if subject_cfg:
        log_event(
            "SUBJECT_CONTEXT_SELECTED",
            message=(
                f"Subject config selected | subject={subject_cfg.id}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "subject_selected",
                "subject": subject_cfg.id,
                "domain": subject_cfg.domain,
                "guidelines_count": len(
                    subject_cfg.pedagogical_guidelines
                ),
            },
        )

    # --- 3. KNOWLEDGE (seulement si matière configurée) ---
    knowledge: dict = {
        "status": "unavailable",
        "items": [],
        "searched_sources": 0,  # fix revue 11
    }
    if subject_cfg:
        knowledge = search_knowledge(
            subject_cfg.id,
            topic=routing.topic,
            query=query,
            limit=max_knowledge,
        )
        if knowledge["items"]:
            log_event(
                "KNOWLEDGE_SELECTED",
                message=(
                    f"Knowledge selected | subject={subject_cfg.id} | "
                    f"items={len(knowledge['items'])} | "
                    f"status={knowledge['status']}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "knowledge_selected",
                    "subject": subject_cfg.id,
                    "knowledge_items": [
                        f"{i['source']}/{i['topic']}"
                        for i in knowledge["items"]
                    ],
                    "knowledge_status": knowledge["status"],
                },
            )

    # --- 4. TOOLS ---
    tools_ctx = build_tool_context(routing.subject)

    # --- 5. USER MEMORY (pertinence query + fill minimal §39) ---
    relevant = _select_memories(user_id, query, max_memories)

    try:
        profile = read_profile(user_id)
    except Exception:
        profile = {"name": None, "description": None}

    user_ctx = build_user_context(user_id, profile, relevant)

    # --- 6. THREAD STATE ---
    thread_ctx = build_thread_context(thread_id)

    context = {
        "router": {
            "subject": routing.subject,
            "topic": routing.topic,
            "confidence": routing.confidence,
            "status": routing.status,
            "candidates": routing.candidates,
            "subjects": routing.subjects,  # fix revue 6
        },
        "subject": (
            {
                "id": subject_cfg.id,
                "name": subject_cfg.name,
                "domain": subject_cfg.domain,
                "description": subject_cfg.description,
                "teaching_style": subject_cfg.teaching_style,
                "pedagogical_guidelines": subject_cfg.pedagogical_guidelines,
                "capabilities": subject_cfg.capabilities,
            }
            if subject_cfg
            else None
        ),
        "knowledge": knowledge,
        "tools": tools_ctx,
        "user": user_ctx,
        "thread": thread_ctx,
        "learning": None,
        "relevant_memories": relevant,
        "stats": {
            "memories_used": len(relevant),
            "knowledge_items": len(knowledge["items"]),
            "user_context_chars": len(user_ctx.get("text", "")),
            "context_size": (
                len(user_ctx.get("text", ""))
                + len(thread_ctx.get("text", ""))
                + sum(
                    len(i["content"])
                    for i in knowledge["items"]
                )
            ),
        },
    }

    log_event(
        "CONTEXT_BUILD_END",
        message=(
            f"Context built | user={user_id} | "
            f"subject={routing.subject} | status={routing.status} | "
            f"memories={len(relevant)} | "
            f"knowledge={len(knowledge['items'])}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "context_build",
            "subject": routing.subject,
            "topic": routing.topic,
            "routing_status": routing.status,
            "memory_items": len(relevant),
            "knowledge_items": len(knowledge["items"]),
            "tools": tools_ctx["available_count"],
            "context_size": context["stats"]["context_size"],
            "user_memory_selected": [
                f.get("id") for f in relevant
            ][:12],
            "thread_context_selected": bool(
                thread_ctx.get("thread_id")
            ),
        },
    )
    return context
