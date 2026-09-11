# Context Builder V5 — assemble le contexte métier en objet STRUCTURÉ.
#
# Rôle (§10/§71) : collecter + sélectionner + prioriser + structurer.
# NE REMPLACE PAS les mécanismes LangChain : il les CONSOMME.
#   - Routing     : app.context.router (RoutingResult pydantic)
#   - Config      : app.subjects.registry (SubjectConfig YAML)
#   - Knowledge   : app.context.knowledge_retriever
#   - Tools       : app.subjects.tool_registry (resolve_tools)
#   - User memory : app.agent.memory (SqliteStore, namespace user)
#   - Thread      : app.context.thread_context (léger, §32)
#
# Sortie : BuiltContext (pydantic, §30) — consommé par le
# Prompt Builder et par l'API preview. Plus de dict brut.
from app.agent.memory import (
    list_facts,
    read_profile,
    search_facts,
)
from app.context.knowledge_retriever import search_knowledge
from app.context.router import route_subject
from app.context.schemas import (
    BuiltContext,
    ContextStats,
    KnowledgeResult,
    KnowledgeSearchResult,
    ResolvedTools,
    RoutingResult,
    SubjectContextInfo,
    ThreadContextInfo,
    UserContextInfo,
)
from app.context.thread_context import build_thread_context
from app.context.user_context import build_user_context
from app.logging.events import log_event
from app.subjects.registry import get_subject
from app.subjects.tool_registry import resolve_tools_for_subject

__all__ = [
    "build_context",
    "build_user_context",
    "build_thread_context",
    "build_system_prompt",
    "route_subject",
]

from app.context.prompt_builder import build_system_prompt


def _select_memories(
    user_id: str, query: str, max_memories: int
) -> list[dict]:
    """Sélection mémoire (§31/§45) :

    1. Search par pertinence query (toutes catégories).
    2. Fill SEULEMENT si la search n'a rien retourné — et le fill
       ne prend QUE les catégories de personnalisation
       (identity/background/personality/preference). Les
       `interest` ne sont JAMAIS fill : topiquement déterminés,
       ils n'entrent dans le contexte que via la search (§45 :
       « préfère les exemples pratiques » oui, « aime la
       robotique » non pour une question Python).
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
        # Catégories de personnalisation uniquement — pas interest
        fill_cats = (
            "identity",
            "background",
            "personality",
            "preference",
        )
        try:
            all_facts = list_facts(user_id)
        except Exception:
            all_facts = []
        eligible = [
            f for f in all_facts if f.get("category") in fill_cats
        ]
        if eligible:
            core = [
                f
                for f in eligible
                if f.get("category")
                in ("identity", "background")
            ]
            others = [
                f
                for f in eligible
                if f.get("category")
                not in ("identity", "background")
            ]
            fill = core[:1] + list(reversed(others))[:2]
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
) -> BuiltContext:
    """Construit le contexte complet d'un appel LLM (V5 structuré).

    Retourne BuiltContext (pydantic validé) — routing, subject,
    knowledge, tools, user, thread, stats. Émet CONTEXT_BUILD_START/
    END + SELECTED_* par source.
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

    # --- 1. ROUTING (RoutingResult pydantic) ---
    routing: RoutingResult = route_subject(query, hint_subject=subject)

    # --- 2. SUBJECT CONFIG (Registry — jamais reconstruit par le LLM, §12) ---
    cfg = get_subject(routing.subject) if routing.subject else None
    subject_info: SubjectContextInfo | None = None
    if cfg:
        subject_info = SubjectContextInfo(
            id=cfg.id,
            name=cfg.name,
            domain=cfg.domain,
            description=cfg.description,
            teaching_style=cfg.teaching_style,
            pedagogical_guidelines=cfg.pedagogical_guidelines,
            capabilities=cfg.capabilities,
        )
        log_event(
            "SUBJECT_CONTEXT_SELECTED",
            message=(
                f"Subject config selected | subject={cfg.id}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "subject_selected",
                "subject": cfg.id,
                "domain": cfg.domain,
                "guidelines_count": len(cfg.pedagogical_guidelines),
            },
        )

    # --- 3. KNOWLEDGE (seulement si matière configurée) ---
    knowledge = KnowledgeSearchResult(status="unavailable")
    if cfg:
        raw = search_knowledge(
            cfg.id,
            topic=routing.topic,
            query=query,
            limit=max_knowledge,
        )
        knowledge = KnowledgeSearchResult(
            status=raw["status"],
            items=[
                KnowledgeResult(
                    source=i["source"],
                    topic=i["topic"],
                    content=i["content"],
                    relevance=i.get("relevance", 0.0),
                )
                for i in raw["items"]
            ],
            searched_sources=raw.get("searched_sources", 0),
        )
        if knowledge.items:
            log_event(
                "KNOWLEDGE_SELECTED",
                message=(
                    f"Knowledge selected | subject={cfg.id} | "
                    f"items={len(knowledge.items)} | "
                    f"status={knowledge.status}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "knowledge_selected",
                    "subject": cfg.id,
                    "knowledge_items": [
                        f"{i.source}/{i.topic}"
                        for i in knowledge.items
                    ],
                    "knowledge_status": knowledge.status,
                },
            )
        elif knowledge.status == "unavailable":
            log_event(
                "KNOWLEDGE_UNAVAILABLE",
                level="WARNING",
                message=(
                    f"Knowledge unavailable | subject={cfg.id}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "knowledge_selected",
                    "subject": cfg.id,
                    "knowledge_status": knowledge.status,
                },
            )

    # --- 4. TOOLS (resolve_tools — §28/§39) ---
    available_tools, unavailable_tools = resolve_tools_for_subject(
        routing.subject
    )
    tools = ResolvedTools(
        available=available_tools,
        declared=sorted(set(available_tools + unavailable_tools)),
        unavailable=unavailable_tools,
    )
    log_event(
        "TOOLS_SELECTED",
        message=(
            f"Tools selected | subject={routing.subject} | "
            f"available={len(tools.available)} | "
            f"unavailable={len(tools.unavailable)}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "tools_selected",
            "subject": routing.subject or "",
            "tools_available": tools.available,
            "tools_unavailable": tools.unavailable,
        },
    )

    # --- 5. USER MEMORY (Store longue durée, namespace user) ---
    relevant = _select_memories(user_id, query, max_memories)

    try:
        profile = read_profile(user_id)
    except Exception:
        profile = {"name": None, "description": None}

    user_ctx_raw = build_user_context(user_id, profile, relevant)
    user = UserContextInfo(
        text=user_ctx_raw.get("text", ""),
        facts_count=user_ctx_raw.get("facts_count", 0),
    )

    # --- 6. THREAD STATE (léger — métadonnées, §32) ---
    thread_ctx_raw = build_thread_context(thread_id)
    thread = ThreadContextInfo(
        thread_id=thread_ctx_raw.get("thread_id", ""),
        message_count=thread_ctx_raw.get("message_count"),
        text=thread_ctx_raw.get("text", ""),
    )

    stats = ContextStats(
        memories_used=len(relevant),
        knowledge_items=len(knowledge.items),
        user_context_chars=len(user.text),
        context_size=(
            len(user.text)
            + len(thread.text)
            + sum(len(i.content) for i in knowledge.items)
        ),
    )

    context = BuiltContext(
        routing=routing,
        subject=subject_info,
        knowledge=knowledge,
        tools=tools,
        user=user,
        thread=thread,
        learning=None,
        relevant_memories=relevant,
        stats=stats,
    )

    log_event(
        "CONTEXT_BUILD_END",
        message=(
            f"Context built | user={user_id} | "
            f"subject={routing.subject} | status={routing.status} | "
            f"memories={stats.memories_used} | "
            f"knowledge={stats.knowledge_items}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "context_build",
            "subject": routing.subject,
            "topic": routing.topic,
            "routing_status": routing.status,
            "memory_items": stats.memories_used,
            "knowledge_items": stats.knowledge_items,
            "tools": len(tools.available),
            "context_size": stats.context_size,
            "user_memory_selected": [
                f.get("id") for f in relevant
            ][:12],
            "thread_context_selected": bool(thread.thread_id),
        },
    )
    return context
