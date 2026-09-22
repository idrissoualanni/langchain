# Research Subgraph — NODES + graphe compilé (V1, DÉTERMINISTE).
#
# Pipeline :
#
#   START
#    ↓
#   plan           → build_research_plan (requêtes bornées)
#    ↓
#   research       → web_search (multi-tâches, retry transitoire borné,
#                    timeout par appel, scraping de secours)
#       ↺ (tasks restantes et iteration < max_iterations)
#    ↓
#   extract_claims → claims / faits structurés (données, injection-safe)
#    ↓
#   verify         → compare_sources (corroboration, contradictions)
#    ↓
#   synthesize     → rapport + ResearchResult (§8) dans workflow_result
#    ↓
#   END
#
# Boucle BORNÉE LangGraph (conditional edges) : le node `research`
# consomme UNE tâche par invocation ; le routeur reboucle tant que
# tasks reste non vide ET iteration < max_iterations. Retries
# uniquement sur erreurs TRANSOIRES (statut "error" / timeout), bornés
# par MAX_SEARCH_RETRIES par tâche. Aucun while illimité.
#
# Sécurité :
#   - contenu web = données, jamais instructions (cf. claims.py) ;
#   - aucune exécution de code ; aucun secret manipulé ;
#   - timeout sur chaque appel web (SEARCH_TIMEOUT_S, scraping lui
#     même borné par web_scraper).
#
# N'EXPOSE AU MAIN QUE workflow_result (ResearchResult.model_dump()).
from __future__ import annotations

import threading

from langgraph.graph import END, START, StateGraph

from app.schemas.workflow import ResearchResult
from app.graph.subgraphs.research.claims import (
    compare_sources,
    extract_claims_from_sources,
    synthesize_report,
)
from app.graph.subgraphs.research.planner import (
    DEFAULT_MAX_QUERIES,
    build_research_plan,
)
from app.graph.subgraphs.research.state import ResearchState
from app.logging.events import log_event

# Borne de la boucle (défaut 4, cf. mission).
DEFAULT_MAX_ITERATIONS = 4
# Retries par tâche, UNIQUEMENT sur erreur transitoire (statut error
# ou timeout) — borné.
MAX_SEARCH_RETRIES = 2
# Timeout de chaque appel web (recherche).
SEARCH_TIMEOUT_S = 25.0

# --- Indirections INJECTABLES (tests déterministes) ----------------
# Points d'override SANS modifier le code existant : les tests
# remplacent web_search_fn par un stub (aucun réseau réel) et
# scrape_fn par un faux scraper si besoin. Aucune dépendance.
web_search_fn = None
scrape_fn = None


def _default_web_search(
    query: str,
    subject=None,
    topic=None,
    language: str = "fr",
    user_id: str = "",
    thread_id: str = "",
):
    """Recherche web réelle (app.context.web_search — chaîne existante,
    ranking + scraping intégrés). Résout l'import à l'appel pour éviter
    tout cycle d'import au module."""
    from app.context.web_search import web_search

    return web_search(
        query,
        subject=subject,
        topic=topic,
        language=language,
        top_k=3,
        user_id=user_id,
        thread_id=thread_id,
    )


def _default_scrape(url: str, user_id: str = "", thread_id: str = ""):
    """Scraping de secours (app.context.web_scraper, fail-safe)."""
    from app.context.web_scraper import fetch_page_content

    return fetch_page_content(url, user_id=user_id, thread_id=thread_id)


def _ids(state) -> tuple[str, str]:
    user_id = (state or {}).get("user_id") or ""
    thread_id = (state or {}).get("thread_id") or ""
    return user_id, thread_id


def _log(name, message, state, level="INFO", extra=None):
    user_id, thread_id = _ids(state)
    log_event(
        name,
        level=level,
        message=message,
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "research_subgraph", **(extra or {})},
    )


# ------------------------------------------------------------
# Helpers web (timeout + injection)
# ------------------------------------------------------------
def _run_with_timeout(fn, timeout_s: float) -> tuple[str, object]:
    """Exécute fn dans un thread daemon avec timeout borné.

    Retour : ("ok", valeur) | ("timeout", None) | ("error", exc).
    Aucun appel ne peut bloquer le graphe au-delà de timeout_s.
    """
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 — collecté, jamais propagé
            box["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return "timeout", None
    if "error" in box:
        return "error", box["error"]
    return "ok", box.get("value")


def _run_web_search(query, subject, topic, language, user_id, thread_id):
    """Appel web avec timeout — retourne (response|None, erreur|None)."""
    fn = web_search_fn or _default_web_search

    def call():
        return fn(
            query,
            subject=subject,
            topic=topic,
            language=language,
            user_id=user_id,
            thread_id=thread_id,
        )

    status, payload = _run_with_timeout(call, SEARCH_TIMEOUT_S)
    if status == "timeout":
        return None, f"timeout après {SEARCH_TIMEOUT_S}s"
    if status == "error":
        return None, f"erreur web : {payload}"
    return payload, None


def _scrape_url(url, user_id, thread_id) -> str:
    """Scraping de secours d'UNE url (fail-safe) — contenu ou "". """
    if not url:
        return ""
    try:
        fn = scrape_fn or _default_scrape
        status, text = fn(url, user_id=user_id, thread_id=thread_id)
        if status == "scraped" and text:
            return str(text)
    except Exception:  # noqa: BLE001 — le scraper est fail-safe de base
        pass
    return ""


def _status_of(resp) -> str:
    if isinstance(resp, dict):
        return resp.get("status") or "error"
    return getattr(resp, "status", None) or "error"


def _results_of(resp) -> list:
    if isinstance(resp, dict):
        return list(resp.get("results") or [])
    return list(getattr(resp, "results", None) or [])


def _result_to_dict(r) -> dict:
    """SearchResult (objet ou dict) → dict normalisé de source."""
    if isinstance(r, dict):
        return {
            "title": str(r.get("title") or ""),
            "source": str(r.get("source") or ""),
            "url": str(r.get("url") or ""),
            "content": str(r.get("content") or ""),
            "snippet": str(r.get("snippet") or ""),
            "relevance": float(r.get("relevance") or 0.0),
            "source_type": str(r.get("source_type") or "web"),
            "metadata": dict(r.get("metadata") or {}),
        }
    return {
        "title": str(getattr(r, "title", None) or ""),
        "source": str(getattr(r, "source", None) or ""),
        "url": str(getattr(r, "url", None) or ""),
        "content": str(getattr(r, "content", None) or ""),
        "snippet": str(getattr(r, "snippet", None) or ""),
        "relevance": float(getattr(r, "relevance", 0.0) or 0.0),
        "source_type": str(getattr(r, "source_type", "web") or "web"),
        "metadata": dict(getattr(r, "metadata", None) or {}),
    }


# ------------------------------------------------------------
# PLAN node — plan de recherche borné + initialisation de l'état
# ------------------------------------------------------------
def plan_node(state) -> dict:
    """PLAN — décompose la question en requêtes web bornées.

    REPLAY-safe : si un plan existe déjà dans l'état (continuation),
    il est conservé (aucune réinitialisation).
    """
    state = state or {}
    question = str(
        state.get("question") or state.get("query") or ""
    ).strip()
    payload = dict(state.get("payload") or {})
    objective = str(
        state.get("objective") or payload.get("objective") or question or ""
    )
    subject = payload.get("subject")
    topic = payload.get("topic")
    language = str(payload.get("language") or "fr")
    max_iterations = int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    max_queries = min(
        max_iterations,
        int(payload.get("max_queries") or DEFAULT_MAX_QUERIES),
    )
    plan_override = payload.get("plan") or None

    existing = [dict(t) for t in (state.get("plan") or [])]
    if existing:
        plan = existing
    else:
        plan = build_research_plan(
            question,
            objective=objective,
            subject=subject,
            topic=topic,
            language=language,
            max_queries=max_queries,
            plan_override=plan_override,
        )
        _log(
            "RESEARCH_PLAN",
            f"Research plan | queries={len(plan)} | max={max_iterations}",
            state,
            extra={"queries": len(plan), "max_iterations": max_iterations},
        )

    return {
        "question": question,
        "objective": objective,
        "plan": plan,
        "tasks": [dict(t) for t in plan],
        "sources": [dict(s) for s in (state.get("sources") or [])],
        "claims": [dict(c) for c in (state.get("claims") or [])],
        "evidence": [dict(e) for e in (state.get("evidence") or [])],
        "findings": [dict(f) for f in (state.get("findings") or [])],
        "contradictions": [
            dict(x) for x in (state.get("contradictions") or [])
        ],
        "missing_information": [
            str(m) for m in (state.get("missing_information") or [])
        ],
        "errors": [dict(e) for e in (state.get("errors") or [])],
        "iteration": int(state.get("iteration") or 0),
        "final_report": None,
    }


# ------------------------------------------------------------
# RESEARCH node — UNE recherche web par invocation (boucle bornée)
# ------------------------------------------------------------
def research_node(state) -> dict:
    """RESEARCH — exécute la recherche web de la prochaine tâche.

    BOUCLE BORNÉE : une invocation consomme UNE tâche (tasks[0]).
    Retry transitoire borné (MAX_SEARCH_RETRIES) en cas de statut
    "error"/timeout, puis la tâche est consommée AVEC un enregistrement
    d'erreur (jamais de blocage ni de boucle infinie). Les erreurs en
    amont (pas de clé, service KO, résultats insuffisants) sont
    collectées dans errors / missing_information et on CONTINUE.
    """
    state = state or {}
    tasks = [dict(t) for t in (state.get("tasks") or [])]
    if not tasks:
        return {}
    task = tasks[0]
    query = str(task.get("query") or "").strip()
    user_id, thread_id = _ids(state)
    errors = [dict(e) for e in (state.get("errors") or [])]
    missing = [str(m) for m in (state.get("missing_information") or [])]
    sources = [dict(s) for s in (state.get("sources") or [])]

    resp = None
    last_err = ""
    for attempt in range(MAX_SEARCH_RETRIES + 1):
        resp, last_err = _run_web_search(
            query,
            task.get("subject"),
            task.get("topic"),
            str(task.get("language") or "fr"),
            user_id,
            thread_id,
        )
        if resp is None:
            continue
        if _status_of(resp) != "error":
            break
        last_err = "erreur réseau persistante"
    else:
        resp = None

    if resp is None:
        errors.append(
            {
                "task": query[:140],
                "kind": "search_error",
                "detail": str(last_err or "échec de recherche")[:200],
                "attempts": MAX_SEARCH_RETRIES + 1,
            }
        )
        missing.append(f"Recherche impossible : {query[:100]}")
    else:
        status = _status_of(resp)
        if status == "found":
            before = len(sources)
            results = _results_of(resp)
            for r in results:
                d = _result_to_dict(r)
                if d.get("url") and not any(
                    s.get("url") == d["url"] for s in sources
                ):
                    sources.append(d)
            # Scraping de secours (web_scraper) pour les sources SANS
            # contenu enrichi par le provider (échec partiel §32).
            for d in sources[before:]:
                if not str(d.get("content") or "").strip():
                    text = _scrape_url(d.get("url"), user_id, thread_id)
                    if text:
                        d["content"] = text
                        if isinstance(d.get("metadata"), dict):
                            d["metadata"]["scraped"] = "yes"
            if len(sources) == before:
                missing.append(
                    f"Résultats sans contenu exploitable : {query[:100]}"
                )
        elif status == "insufficient":
            missing.append(f"Résultats insuffisants : {query[:100]}")
        else:  # unavailable / erreur non retentée
            errors.append(
                {
                    "task": query[:140],
                    "kind": "search_error",
                    "detail": f"statut web : {status}",
                    "attempts": MAX_SEARCH_RETRIES + 1,
                }
            )
            missing.append(f"Service de recherche indisponible : {query[:100]}")

    remaining = tasks[1:]
    iteration = int(state.get("iteration") or 0) + 1
    max_iterations = int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    _log(
        "RESEARCH_STEP",
        f"research step | query={query[:60]} | iteration={iteration}/"
        f"{max_iterations} | remaining={len(remaining)}",
        state,
        extra={
            "iteration": iteration,
            "remaining": len(remaining),
            "sources": len(sources),
        },
    )
    return {
        "tasks": remaining,
        "sources": sources,
        "errors": errors,
        "missing_information": missing,
        "iteration": iteration,
    }


def route_after_research(state) -> str:
    """Routeur interne de la boucle bornée :
      - "research"      → tant que tasks restent ET iteration < borne ;
      - sinon           → "extract_claims" (fin de collecte).
    """
    state = state or {}
    tasks = state.get("tasks") or []
    iteration = int(state.get("iteration") or 0)
    max_iterations = int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    if tasks and iteration < max_iterations:
        return "research"
    return "extract_claims"


# ------------------------------------------------------------
# EXTRACT_CLAIMS node — faits/claims structurés (données, safe)
# ------------------------------------------------------------
def extract_claims_node(state) -> dict:
    """EXTRACT_CLAIMS — extraction déterministe de claims depuis les
    sources (contenu traité comme DONNÉES, jamais comme instructions)."""
    state = state or {}
    question = str(state.get("question") or state.get("query") or "")
    sources = [dict(s) for s in (state.get("sources") or [])]
    claims = extract_claims_from_sources(sources, question)
    _log(
        "RESEARCH_EXTRACT",
        f"research extract | sources={len(sources)} | claims={len(claims)}",
        state,
        extra={"sources": len(sources), "claims": len(claims)},
    )
    return {"claims": claims}


# ------------------------------------------------------------
# VERIFY node — comparaison de sources (corroboration/contradictions)
# ------------------------------------------------------------
def verify_node(state) -> dict:
    """VERIFY — vérifie les claims entre sources : corroboration,
    contradictions, limites de cross-check (missing_information)."""
    state = state or {}
    claims = [dict(c) for c in (state.get("claims") or [])]
    sources = [dict(s) for s in (state.get("sources") or [])]
    comparison = compare_sources(claims, sources)

    existing = [str(m) for m in (state.get("missing_information") or [])]
    for m in comparison.get("missing_information") or []:
        if str(m) not in existing:
            existing.append(str(m))

    _log(
        "RESEARCH_VERIFY",
        f"research verify | contradictions={len(comparison['contradictions'])} "
        f"| corroborated={sum(1 for e in comparison['evidence'] if e['verdict'] == 'corroborated')}",
        state,
        extra={
            "contradictions": len(comparison["contradictions"]),
            "evidence": len(comparison["evidence"]),
        },
    )
    return {
        "evidence": comparison.get("evidence", []),
        "contradictions": comparison.get("contradictions", []),
        "findings": comparison.get("findings", []),
        "missing_information": existing,
    }


# ------------------------------------------------------------
# SYNTHESIZE node — rapport + ResearchResult (§8)
# ------------------------------------------------------------
def synthesize_node(state) -> dict:
    """SYNTHESIZE — synthèse sourcée, rapport structuré et
    ResearchResult (§8) dans workflow_result. N'expose que la sortie
    structurée au Main — jamais l'état interne."""
    state = state or {}
    question = str(state.get("question") or state.get("query") or "")
    objective = str(state.get("objective") or "")
    plan = [dict(t) for t in (state.get("plan") or [])]
    iteration = int(state.get("iteration") or 0)
    max_iterations = int(state.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    consumed = min(iteration, len(plan))
    plan_queries = [
        str(t.get("query") or "") for t in plan[:consumed] if t.get("query")
    ]

    sources = [dict(s) for s in (state.get("sources") or [])]
    claims = [dict(c) for c in (state.get("claims") or [])]
    evidence = [dict(e) for e in (state.get("evidence") or [])]
    findings = [dict(f) for f in (state.get("findings") or [])]
    contradictions = [dict(x) for x in (state.get("contradictions") or [])]
    missing = [str(m) for m in (state.get("missing_information") or [])]
    errors = [dict(e) for e in (state.get("errors") or [])]

    report, summary = synthesize_report(
        question=question,
        objective=objective,
        plan_queries=plan_queries,
        sources=sources,
        claims=claims,
        evidence=evidence,
        findings=findings,
        contradictions=contradictions,
        missing_information=missing,
        errors=errors,
        iteration=iteration,
        max_iterations=max_iterations,
    )

    if claims and sources:
        status = "ok"
        message = (
            f"Recherche terminée : {len(sources)} source(s), "
            f"{len(claims)} fait(s) extrait(s)."
        )
    elif sources:
        status = "partial"
        message = "Recherche partielle : sources récupérées mais aucun fait exploitable."
    elif errors:
        status = "error"
        message = "Recherche en échec : aucune source exploitable."
    else:
        status = "partial"
        message = "Recherche sans résultat."

    result = ResearchResult(
        workflow="research",
        status=status,
        message=message,
        plan=plan_queries,
        claims=[
            {
                "claim": c.get("claim", ""),
                "source": c.get("source", ""),
                "confidence": float(c.get("confidence", 0.0) or 0.0),
            }
            for c in claims
        ],
        summary=summary,
    )

    _log(
        "RESEARCH_SYNTHESIZE",
        f"research synthesize | status={status} | sources={len(sources)} "
        f"| claims={len(claims)}",
        state,
        extra={"status": status, "sources": len(sources), "claims": len(claims)},
    )
    return {
        "final_report": report,
        "workflow_result": result.model_dump(),
    }


# ------------------------------------------------------------
# Compilation + helpers d'entrée
# ------------------------------------------------------------
def build_initial_state(
    query: str,
    user_id: str = "",
    thread_id: str = "",
    payload: dict | None = None,
    question: str | None = None,
    objective: str | None = None,
    max_iterations: int | None = None,
) -> dict:
    """État initial du subgraph (stateless, testable isolément).

    Le subgraph est autonome : n'importe quel orchestrateuor peut
    construire cet état et invoquer le graphe — il n'est PAS câblé au
    Main Graph ici (câblage = un autre agent).
    """
    payload = dict(payload or {})
    return {
        "user_id": user_id or "",
        "thread_id": thread_id or "",
        "query": query or "",
        "payload": payload,
        "question": question if question is not None else (query or ""),
        "objective": objective
        if objective is not None
        else str(payload.get("objective") or ""),
        "max_iterations": int(
            max_iterations
            if max_iterations is not None
            else (payload.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
        ),
    }


def compile_research_subgraph():
    """Compile le ResearchSubgraph (V1) sur ResearchState.

    Aucun checkpointer/store requis : sous-graphe DÉTERMINISTE et
    stateless (l'état transite par l'invocation). Peut être ajouté
    comme node du Main Graph via add_node("research", ...) — seuls les
    canaux partagés (workflow_result) transitent, les champs internes
    restent contenus.
    """
    graph = StateGraph(ResearchState)

    graph.add_node("plan", plan_node)
    graph.add_node("research", research_node)
    graph.add_node("extract_claims", extract_claims_node)
    graph.add_node("verify", verify_node)
    graph.add_node("synthesize", synthesize_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "research")
    graph.add_conditional_edges(
        "research",
        route_after_research,
        {"research": "research", "extract_claims": "extract_claims"},
    )
    graph.add_edge("extract_claims", "verify")
    graph.add_edge("verify", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


def invoke_research_workflow(
    query: str,
    user_id: str = "",
    thread_id: str = "",
    payload: dict | None = None,
    max_iterations: int | None = None,
) -> ResearchResult:
    """Exécution synchrone complète → ResearchResult (§8)."""
    initial = build_initial_state(
        query,
        user_id=user_id,
        thread_id=thread_id,
        payload=payload,
        max_iterations=max_iterations,
    )
    final_state = compile_research_subgraph().invoke(initial)
    wf = final_state.get("workflow_result") or {}
    if wf:
        return ResearchResult(**wf)
    return ResearchResult(
        workflow="research",
        status="error",
        message="Aucun résultat produit par le subgraph.",
        plan=[],
    )


async def run_research_workflow(
    query: str,
    user_id: str = "",
    thread_id: str = "",
    payload: dict | None = None,
    max_iterations: int | None = None,
) -> ResearchResult:
    """Exécution async complète → ResearchResult (§8)."""
    initial = build_initial_state(
        query,
        user_id=user_id,
        thread_id=thread_id,
        payload=payload,
        max_iterations=max_iterations,
    )
    final_state = await compile_research_subgraph().ainvoke(initial)
    wf = final_state.get("workflow_result") or {}
    if wf:
        return ResearchResult(**wf)
    return ResearchResult(
        workflow="research",
        status="error",
        message="Aucun résultat produit par le subgraph.",
        plan=[],
    )


__all__ = [
    "compile_research_subgraph",
    "run_research_workflow",
    "invoke_research_workflow",
    "build_initial_state",
    "plan_node",
    "research_node",
    "route_after_research",
    "extract_claims_node",
    "verify_node",
    "synthesize_node",
    "web_search_fn",
    "scrape_fn",
    "DEFAULT_MAX_ITERATIONS",
    "MAX_SEARCH_RETRIES",
    "SEARCH_TIMEOUT_S",
]