# Context Builder V5+V6 — assemble le contexte métier en objet STRUCTURÉ.
#
# Rôle (§10/§71) : collecter + sélectionner + prioriser + structurer.
# NE REMPLACE PAS les mécanismes LangChain : il les CONSOMME.
#   - Routing     : app.context.router (RoutingResult pydantic)
#   - Config      : app.subjects.registry (SubjectConfig YAML)
#   - Knowledge   : app.context.knowledge_retriever
#   - Tools       : app.subjects.tool_registry (resolve_tools)
#   - User memory : app.agent.memory (SqliteStore, namespace user)
#   - Thread      : app.context.thread_context (léger, §32)
#   - Learning    : app.learning.learning_context (V6, §24 —
#                   sélection PERTINENTE, jamais tout le profil)
#
# Sortie : BuiltContext (pydantic, §30) — consommé par le
# Prompt Builder et par l'API preview. Plus de dict brut.
from app.agent.memory import (
    list_facts,
    read_profile,
    search_facts,
)
from app.context.budget import (
    BudgetSection,
    apply_budget,
    build_budget,
    estimate_tokens,
)
from app.context.fallback import (
    decide_fallback,
    fallback_note_for_prompt,
)
from app.context.knowledge_retriever import search_knowledge
from app.context.model_capabilities import (
    get_model_capabilities,
)
from app.context.router import route_subject
from app.context.schemas import (
    ActivityContextInfo,
    BuiltContext,
    ContextStats,
    KnowledgeResult,
    KnowledgeSearchResult,
    ResolvedTools,
    RoutingResult,
    SearchResponse,
    SubjectContextInfo,
    ThreadContextInfo,
    UserContextInfo,
)
from app.context.thread_context import build_thread_context
from app.context.user_context import build_user_context
from app.context.web_search import web_search
from app.learning.learning_context import get_learning_context
from app.learning.schemas import LearningContextInfo
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
    learning_activity: dict | None = None,
) -> BuiltContext:
    """Construit le contexte complet d'un appel LLM (V5 structuré).

    Retourne BuiltContext (pydantic validé) — routing, subject,
    knowledge, tools, user, thread, stats. Émet CONTEXT_BUILD_START/
    END + SELECTED_* par source.

    V6.8.1 §13/§16 : learning_activity (state LangGraph
    thread-local) est optionnel — le builder en expose un RÉSUMÉ
    (ActivityContextInfo) dans BuiltContext.activity, sans jamais
    y mettre les données de l'exercice (question/expected).
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
            "activity": (
                "present"
                if learning_activity
                and learning_activity.get("status")
                not in (None, "idle", "completed", "abandoned")
                else "none"
            ),
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

    # --- 3b. PIPELINE DE FALLBACK V6.5 (§24-§26) ---
    # knowledge insuffisant (parcouru, rien de pertinent) ET
    # matière SUPPORTÉE (§16 : subject_supported ≠ knowledge_found)
    # → tentative WEB. Aucune tentative pour unsupported/unknown :
    # pas de matière = pas d'ancrage de recherche (§36 noise).
    # §26 : knowledge_unavailable n'est JAMAIS transformé en
    # knowledge_found — le statut original est conservé, le web
    # est une SOURCE SÉPARÉE (BuiltContext.web).
    web_response = SearchResponse(status="unavailable")
    if (
        cfg
        and not knowledge.items
        and knowledge.status == "insufficient"
    ):
        log_event(
            "SEARCH_START",
            message=(
                f"Search fallback pipeline | subject={cfg.id} | "
                f"local=insufficient → web"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "search_pipeline",
                "subject": cfg.id,
                "topic": routing.topic or "",
                "query": (query or "")[:100],
                "stage": "web_fallback",
            },
        )
        web_response = web_search(
            user_query=query,
            subject=cfg.id,
            topic=routing.topic,
            language="fr",
            top_k=3,
            user_id=user_id,
            thread_id=thread_id,
        )
        log_event(
            "SEARCH_END",
            message=(
                f"Search pipeline end | subject={cfg.id} | "
                f"web={web_response.status} | "
                f"results={len(web_response.results)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "search_pipeline",
                "subject": cfg.id,
                "topic": routing.topic or "",
                "query": (query or "")[:100],
                "status": web_response.status,
                "result_count": len(web_response.results),
                "best_relevance": (
                    web_response.results[0].relevance
                    if web_response.results
                    else None
                ),
            },
        )
        # §28 : événement résultat/no-result dédié
        if web_response.results:
            log_event(
                "SEARCH_RESULT",
                message=(
                    f"Search results | count="
                    f"{len(web_response.results)} | best="
                    f"{web_response.results[0].relevance}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "search_pipeline",
                    "subject": cfg.id,
                    "topic": routing.topic or "",
                    "query": (query or "")[:100],
                    "result_count": len(web_response.results),
                    "best_relevance": (
                        web_response.results[0].relevance
                    ),
                    "sources": [
                        r.source for r in web_response.results
                    ][:5],
                },
            )
        else:
            log_event(
                "SEARCH_NO_RESULT",
                level="WARNING",
                message=(
                    f"Search no result | web="
                    f"{web_response.status} → General Tutor"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "search_pipeline",
                    "subject": cfg.id,
                    "topic": routing.topic or "",
                    "query": (query or "")[:100],
                    "status": web_response.status,
                    "result_count": 0,
                },
            )

    # --- 3c. FALLBACK DECISION (V6.6 §6) — matrice pure ---
    # Consomme routing/knowledge/web et produit UNE action
    # explicite. Testable sans LLM (decide_fallback pur).
    fallback = decide_fallback(
        routing_status=routing.status,
        subject=routing.subject,
        topic=routing.topic,
        knowledge_status=knowledge.status,
        web_status=web_response.status,
        has_web_results=bool(web_response.results),
        query=query,
        user_id=user_id,
        thread_id=thread_id,
    )
    if routing.status == "ambiguous":
        # §10 : candidates transmis pour la clarification
        fallback.candidates = list(routing.candidates)

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

    # --- 7. LEARNING PROFILE (V6 §24 — sélection pertinente) ---
    # Jamais tout le profil : get_learning_context ne remonte que
    # l'état du subject/topic routé (§25). Absence = not_started
    # (§26), jamais une erreur.
    learning: LearningContextInfo = get_learning_context(
        user_id=user_id,
        subject=routing.subject,
        topic=routing.topic,
        thread_id=thread_id,
    )

    # --- 7b. CONTEXT BUDGET (V6.8 §40-§47) ---
    # Sections par priorité §41 : P0 (system/message/activité)
    # ne passent PAS par le builder — intouchables par contrat
    # (§43/§46). Ici : P1 learning, P2 knowledge/web, P3 mémoire,
    # P4 thread.
    caps = get_model_capabilities()
    budget = build_budget(caps)

    def _sec(key: str, prio: int, text: str, payload=None):
        return BudgetSection(
            key=key,
            priority=prio,
            tokens=estimate_tokens(text),
            payload=payload,
        )

    budget_sections = [
        _sec("learning", 1, str(learning.model_dump())),
        _sec(
            "knowledge", 2,
            "\n".join(i.content for i in knowledge.items),
        ),
    ]
    if web_response.results:
        budget_sections.append(
            _sec(
                "web_search", 2,
                "\n".join(
                    (r.content or "") + (r.snippet or "")
                    for r in web_response.results
                ),
                [r.model_dump() for r in web_response.results],
            )
        )
    if user.text:
        budget_sections.append(
            _sec("user_memory", 3, user.text)
        )
    if thread.text:
        budget_sections.append(_sec("thread", 4, thread.text))

    budget_result = apply_budget(
        budget_sections,
        window=caps.context_window,
        reserved=caps.reserved_output_tokens,
    )

    # Appliquer les décisions du budget au BuiltContext.
    # P0/P1 learning n'est jamais droppé par apply_budget (P1)
    # — la branche learning ci-dessous est une défense théorique.
    # V6.8.1 §17 : les sections droppées sont RECONSTRUITES
    # (nouvelles instances), l'original KnowledgeSearchResult/
    # SearchResponse n'est jamais muté en place — items et
    # results restent synchronisés (validateur §8).
    if "thread" in budget_result.dropped_keys:
        thread.text = ""
    if "user_memory" in budget_result.dropped_keys:
        user.text = ""
        relevant = []
    if "web_search" in budget_result.dropped_keys:
        web_response = web_response.model_copy(
            update={"results": []}
        )
    else:
        web_kept = [
            s for s in budget_result.kept
            if s.key == "web_search"
        ]
        if (
            web_kept
            and web_kept[0].payload is not None
            and len(web_kept[0].payload) != len(
                web_response.results
            )
        ):
            # top_k réduit (§44) : garder les premiers (ordre
            # de pertinence du ranking déjà trié)
            web_response = web_response.model_copy(
                update={
                    "results": web_response.results[
                        : len(web_kept[0].payload)
                    ]
                }
            )
    if "knowledge" in budget_result.dropped_keys:
        knowledge = knowledge.model_copy(
            update={"items": [], "results": []}
        )

    log_event(
        "CONTEXT_BUDGET",
        message=(
            f"Context budget | status={budget_result.budget_status} "
            f"| est={budget_result.estimated_input_tokens}tok "
            f"| used={budget_result.sources_used} "
            f"dropped={budget_result.sources_dropped}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "context_budget",
            "budget_status": budget_result.budget_status,
            "estimated_input_tokens": (
                budget_result.estimated_input_tokens
            ),
            "context_window": caps.context_window,
            "reserved_output_tokens": (
                caps.reserved_output_tokens
            ),
            "sources_used": budget_result.sources_used,
            "sources_dropped": budget_result.sources_dropped,
            "dropped_keys": budget_result.dropped_keys,
            "model": caps.model_name,
        },
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
        estimated_input_tokens=(
            budget_result.estimated_input_tokens
        ),
        context_window=caps.context_window,
        reserved_output_tokens=caps.reserved_output_tokens,
        available_input_tokens=(
            budget.available_input_tokens
        ),
        budget_status=budget_result.budget_status,
        sources_used=budget_result.sources_used,
        sources_dropped=budget_result.sources_dropped,
    )

    # V6.8.1 §13 : résumé activité thread-locale (vue exposée
    # au contexte — jamais les données de l'exercice). Le state
    # LangGraph reste la source de vérité complète.
    activity_info: ActivityContextInfo | None = None
    if learning_activity and learning_activity.get("status") in (
        "waiting_for_answer",
        "waiting_for_retry",
        "evaluating",
        "giving_hint",
        "checking_understanding",
    ):
        activity_info = ActivityContextInfo(
            activity_id=learning_activity.get(
                "activity_id", ""
            ),
            activity_type=learning_activity.get(
                "activity_type", ""
            ),
            status=learning_activity.get("status", ""),
            subject=learning_activity.get("subject", ""),
            topic=learning_activity.get("topic", ""),
            hint_level=learning_activity.get("hint_level", 0),
            attempts=learning_activity.get("attempts", 0),
        )

    context = BuiltContext(
        routing=routing,
        subject=subject_info,
        knowledge=knowledge,
        web=web_response,
        fallback=fallback,
        tools=tools,
        user=user,
        thread=thread,
        # V6.8.1 §20 : learning TYPÉ (LearningContextInfo) —
        # plus de dict anonyme. Vue dict historique : learning_dict().
        learning=learning,
        relevant_memories=relevant,
        stats=stats,
        # V6.8.1 §16 : le budget détaillé et le modèle ont un
        # propriétaire dans l'agrégé canonique.
        budget=budget,
        model=caps,
        activity=activity_info,
    )

    log_event(
        "CONTEXT_BUILD_END",
        message=(
            f"Context built | user={user_id} | "
            f"subject={routing.subject} | status={routing.status} | "
            f"memories={stats.memories_used} | "
            f"knowledge={stats.knowledge_items} | "
            f"learning={learning.status} | "
            f"fallback={fallback.action}"
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
            "learning_items": (
                1 if learning.status == "active" else 0
            ),
            "learning_status": learning.status,
            "learning_mastery": learning.mastery,
            "tools": len(tools.available),
            "context_size": stats.context_size,
            "fallback_action": fallback.action,
            "fallback_reason": fallback.reason[:120],
            "user_memory_selected": [
                f.get("id") for f in relevant
            ][:12],
            "thread_context_selected": bool(thread.thread_id),
        },
    )
    return context
