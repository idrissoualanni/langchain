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
    DocumentContextInfo,
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
# V10 : documents personnels de l'utilisateur (RAG). Import LAZY
# au point d'usage (fail-safe §15) : app.rag.vector_store dépend
# d'app.context.semantic.provider, lui-même sous app.context/__init__
# qui importe ce builder — un import top-level crée un cycle
# vector_store → context → builder → retriever → vector_store.
from app.subjects.registry import get_subject
from app.subjects.tool_registry import resolve_tools_for_subject

__all__ = [
    "build_context",
    "retrieve_sources",
    "build_user_context",
    "build_thread_context",
    "build_system_prompt",
    "route_subject",
]

from app.context.prompt_builder import build_system_prompt

# V11 §? (Partie C) : marqueurs lexicaux indiquant une demande qui
# CIBLE EXPLICITEMENT un document personnel (RAG V10) plutôt qu'un
# sujet de cours. La détection est volontairement simple et rapide
# (règles booléennes, zéro NLP — le LLM contrôle déjà la sémantique).
_DOCUMENT_TARGET_MARKERS = (
    "mon document",
    "mes documents",
    "mon cours",
    "mes cours",
    "ma fiche",
    "mes fiches",
    "mes notes",
    "mon pdf",
    "ce document",
    "ce pdf",
    "mon fichier",
    "les documents",
    "mes fichiers",
    "sur le document",
    "ton document",
    "le document fourni",
)


def _query_targets_document(query: str | None) -> bool:
    """Détecte si la requête cible explicitement un document (V11 C).

    True seulement quand la demande porte sur la base documentaire
    personnelle (« évalue-moi sur mon document », « résume mon
    cours »...). Utilisé pour élever la priorité de la section
    user_documents (P2 → P1, jamais droppée §43) : le contenu du
    document devient la source PRINCIPALE du run.
    """
    if not query:
        return False
    q = query.lower()
    return any(m in q for m in _DOCUMENT_TARGET_MARKERS)


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


def retrieve_sources(
    user_id: str,
    thread_id: str,
    query: str,
    routing: RoutingResult,
    cfg,
    max_knowledge: int = 3,
    knowledge: "KnowledgeSearchResult | None" = None,
    web: "SearchResponse | None" = None,
) -> tuple["KnowledgeSearchResult", "SearchResponse"]:
    """Pipeline KNOWLEDGE + WEB (V6.5 §24-§26) — SOURCE DE VÉRITÉ UNIQUE.

    §48 : ni build_context ni le node RETRIEVAL ne dupliquent cette
    logique — c'est LE SEUL endroit qui décide quand le web prend
    le relais du knowledge local.

    Contexte §16/§26 : knowledge UNavailables ≠ knowledge_found ;
    le web est une SOURCE SÉPARÉE (BuiltContext.web). Aucune
    tentative web pour unsupported/unknown (pas d'ancrage, §36).

    V7 ORCHESTRATION : knowledge/web pré-calculés optionnels. Quand
    ils sont fournis, ils sont réutilisés tel quels (le RETRIEVAL
    node a déjà exécuté ce pipeline) ; sinon ils sont calculés ici.
    """
    if knowledge is not None:
        knowledge_result = knowledge
    else:
        knowledge_result = KnowledgeSearchResult(status="unavailable")
        if cfg:
            raw = search_knowledge(
                cfg.id,
                topic=routing.topic,
                query=query,
                limit=max_knowledge,
            )
            knowledge_result = KnowledgeSearchResult(
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
            if knowledge_result.items:
                log_event(
                    "KNOWLEDGE_SELECTED",
                    message=(
                        f"Knowledge selected | subject={cfg.id} | "
                        f"items={len(knowledge_result.items)} | "
                        f"status={knowledge_result.status}"
                    ),
                    user_id=user_id,
                    thread_id=thread_id,
                    extra={
                        "operation": "knowledge_selected",
                        "subject": cfg.id,
                        "knowledge_items": [
                            f"{i.source}/{i.topic}"
                            for i in knowledge_result.items
                        ],
                        "knowledge_status": knowledge_result.status,
                    },
                )
            elif knowledge_result.status == "unavailable":
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
                        "knowledge_status": knowledge_result.status,
                    },
                )

    if web is not None:
        web_response = web
    else:
        web_response = SearchResponse(status="unavailable")
        if (
            cfg
            and not knowledge_result.items
            and knowledge_result.status == "insufficient"
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

    return knowledge_result, web_response


def build_context(
    user_id: str,
    thread_id: str,
    query: str,
    subject: str | None = None,
    topic: str | None = None,
    max_memories: int = 12,
    max_knowledge: int = 3,
    learning_activity: dict | None = None,
    routing: "RoutingResult | None" = None,
    knowledge: "KnowledgeSearchResult | None" = None,
    web: "SearchResponse | None" = None,
    fallback: "FallbackDecision | None" = None,
) -> BuiltContext:
    """Construit le contexte complet d'un appel LLM (V5 structuré).

    Retourne BuiltContext (pydantic validé) — routing, subject,
    knowledge, tools, user, thread, stats. Émet CONTEXT_BUILD_START/
    END + SELECTED_* par source.

    V6.8.1 §13/§16 : learning_activity (state LangGraph
    thread-local) est optionnel — le builder en expose un RÉSUMÉ
    (ActivityContextInfo) dans BuiltContext.activity, sans jamais
    y mettre les données de l'exercice (question/expected).

    V7 ORCHESTRATION : routing / knowledge / web / fallback sont
    des résultats PRÉ-CALCULÉS optionnels (sous-résultats des nodes
    LangGraph). Quand ils sont fournis, le builder LES CONSOMME
    sans ré-exécuter route_subject / search_knowledge / web_search
    / decide_fallback — l'assemblage final reste ici (source de
    vérité unique, §48). Comportement historique inchangé quand
    aucun n'est fourni.
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
    # V7 : routing pré-calculé par le node ROUTER — réutilisé tel
    # quel (route_subject déjà exécuté en amont), sinon appel réel.
    if routing is None:
        routing = route_subject(query, hint_subject=subject)

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
    # --- 3b. PIPELINE DE FALLBACK V6.5 (§24-§26) ---
    # V7 : retrieval pré-calculé par le node RETRIEVAL (source de
    # vérité unique — retrieve_sources, §48), sinon exécution ici.
    knowledge, web_response = retrieve_sources(
        user_id,
        thread_id,
        query,
        routing,
        cfg,
        max_knowledge=max_knowledge,
        knowledge=knowledge,
        web=web,
    )

    # --- 3c. FALLBACK DECISION (V6.6 §6) — matrice pure ---
    # Consomme routing/knowledge/web et produit UNE action
    # explicite. Testable sans LLM (decide_fallback pur).
    # V7 : fallback pré-calculé par le node FALLBACK — le builder
    # ne re-décide pas (source de vérité : les nodes, §48).
    if fallback is not None:
        fallback = fallback.model_copy(
            update={"candidates": []}
        )
    else:
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

    # --- 3d. DOCUMENTS PERSONNELS (RAG V10 §4 + §15 fail-safe) ---
    # Quatrième source de contexte, SÉPARÉE de knowledge/web :
    # c'est la base documentaire PROPRE à l'user_id. Recherche sur
    # TOUTE question (même non routée) : un utilisateur peut avoir
    # indexé ses notes sans rapport direct avec le subject configuré.
    # Jamais d'exception : aucun document = status unavailable →
    # section vide (DocumentContextInfo par défaut), le tuteur
    # garde la conduite normale (§37). Isolation user_id stricte
    # dans RagStore.search (aucun accès cross-user, §15).
    user_documents = DocumentContextInfo(
        text="",
        count=0,
        status="unavailable",
        searched_documents=0,
    )
    try:
        from app.rag.retriever import DocumentRetriever

        # V11 Partie C : une demande qui cible EXPLICITEMENT un
        # document élève la section user_documents (P2 → P1 §41/§46)
        # et augmente le budget de chunks du run.
        document_targeted = _query_targets_document(query)
        if document_targeted:
            log_event(
                "DOCUMENT_TARGET_DETECTED",
                message=(
                    "Document target detected | query target "
                    "explicit | top_k=6 (P1)"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={"query": (query or "")[:120]},
            )
        _retriever = DocumentRetriever()
        doc_resp = _retriever.search_documents(
            user_id=user_id,
            query=query,
            top_k=6 if document_targeted else 4,  # MAX_CONTEXT_CHUNKS du retriever
        )
    except Exception:  # pragma: no cover — défensif, fail-safe
        _retriever = None
        doc_resp = None
        document_targeted = False
    if doc_resp is not None and doc_resp.status == "found":
        try:
            doc_text = _retriever._format_results(
                doc_resp.results
            )
        except Exception:  # pragma: no cover — formatage défensif
            doc_text = ""
        user_documents = DocumentContextInfo(
            text=doc_text,
            count=len(doc_resp.results),
            status="found",
            searched_documents=len(doc_resp.results),
        )
        log_event(
            "DOCUMENTS_SELECTED",
            message=(
                f"User documents selected | user={user_id} | "
                f"results={user_documents.count}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "documents_selected",
                "documents_count": user_documents.count,
                "documents_status": user_documents.status,
                "documents_sources": [
                    r.filename for r in doc_resp.results
                ][:6],
            },
        )
    # status found → log DOCUMENTS_SELECTED ; sinon rien : une
    # base vide ou un retrieval sans résultat est la situation
    # NORMALE (rien à loguer en WARNING).

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
    if user_documents.text:
        budget_sections.append(
            _sec(
                # V11 C : priorité dynamique — cible explicite d'un
                # document → P1 (§41/§43 jamais droppée), sinon P2
                # (rang des sources retrieval classiques).
                "user_documents",
                1 if document_targeted else 2,
                user_documents.text,
            )
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
    if "user_documents" in budget_result.dropped_keys:
        user_documents = user_documents.model_copy(
            update={"text": "", "count": 0}
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
        user_documents_count=user_documents.count,
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
        user_documents=user_documents,
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
            "user_documents_selected": user_documents.count,
        },
    )
    return context
