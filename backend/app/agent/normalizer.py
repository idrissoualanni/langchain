# Response Normalizer V6.7 (§26).
#
# Couche de conversion : structures internes (activity state,
# search, fallback, texte LLM) → AgentResponse (contrat public).
#
# Le frontend ne connaît JAMAIS les structures internes des
# tools (§26) ; le normalizer applique les règles §23 (ne jamais
# exposer keyword list / hidden answer / scoring metadata).
#
# Chemin robuste §33 :
#   structured output dispo → le LLM produit directement un
#   AgentResponse-like (via response schema) ;
#   sinon → CE normalizer (normalisation contrôlée) ;
#   sinon → texte standard (type=text).
# Une incapacité de structured output ne casse JAMAIS le chat.
from app.schemas.response import AgentResponse
from app.schemas.context import FallbackDecision
from app.logging.events import log_event

__all__ = [
    "normalize_response",
    "response_from_activity",
    "response_from_search",
    "response_from_clarification",
    "response_from_error",
    "response_from_text",
]

# Champs de data qui NE DOIVENT JAMAIS fuiter (§23)
_FORBIDDEN_DATA_KEYS = {
    "expected_answer",
    "keywords",
    "key_terms",
    "keyword_list",
    "hidden_answer",
    "scoring",
    "scoring_metadata",
    "answer",
}


def _sanitize_data(data: dict | None) -> dict:
    """Retire toute clé interdite (défense en profondeur §23)."""
    if not data:
        return {}
    return {
        k: v
        for k, v in data.items()
        if k not in _FORBIDDEN_DATA_KEYS
    }


def response_from_text(
    message: str,
    activity: dict | None = None,
) -> AgentResponse:
    """Texte LLM standard → AgentResponse type=text.

    Si une activité est en cours et attend l'étudiant, le statut
    public est waiting_for_user (ADDENDUM §3 : c'est LE statut du
    workflow interactif) — sinon completed (§2).
    """
    waiting = False
    if activity:
        status = activity.get("status")
        waiting = status in (
            "waiting_for_answer",
            "waiting_for_retry",
            "checking_understanding",
        )
    return AgentResponse(
        type="text",
        status="waiting_for_user" if waiting else "completed",
        message=message,
        data=_sanitize_data(
            {
                "activity_id": activity.get("activity_id", ""),
                "activity_status": activity.get("status"),
            }
            if activity
            else {}
        ),
    )


def response_from_activity(
    message: str, activity: dict | None
) -> AgentResponse:
    """État d'activité pédagogique → AgentResponse typé.

    Mapping (ADDENDUM §8 — activity.status et AgentResponse.status
    restent DEUX machines distinctes) :
      waiting_for_answer (exercise) → exercise/waiting_for_user
      waiting_for_answer (quiz)     → quiz/waiting_for_user
      waiting_for_answer (code)     → code/waiting_for_user
      waiting_for_retry             → evaluation/waiting_for_user
      checking_understanding        → evaluation/waiting_for_user
      giving_hint                   → hint/waiting_for_user
      evaluating                    → evaluation/running
      completed                     → evaluation/completed
      abandoned                     → evaluation/cancelled
    """
    if not activity or not activity.get("activity_type"):
        return response_from_text(message, activity)

    a_status = activity.get("status") or "idle"
    a_type = activity.get("activity_type")
    data = _sanitize_data(
        {
            "activity_id": activity.get("activity_id", ""),
            "activity_status": a_status,
            "subject": activity.get("subject"),
            "topic": activity.get("topic"),
        }
    )
    actions: list[dict] = []

    if a_status == "waiting_for_answer":
        rtype = (
            "quiz"
            if a_type == "quiz"
            else ("code" if a_type == "code" else "exercise")
        )
        if rtype == "quiz":
            data.update(
                {
                    "question_index": activity.get(
                        "question_index", 0
                    ),
                    "total_questions": activity.get(
                        "total_questions", 0
                    ),
                }
            )
        if rtype == "code":
            data.update(
                {
                    "language": activity.get("language", "python"),
                    "starter_code": activity.get("starter_code", ""),
                }
            )
        actions = [
            {"type": "submit_answer"},
            {"type": "request_hint"},
        ]
        return AgentResponse(
            type=rtype,
            status="waiting_for_user",
            message=message,
            data=data,
            actions=actions,
        )

    if a_status in ("waiting_for_retry",
                    "checking_understanding"):
        data["next_action"] = "retry_answer"
        return AgentResponse(
            type="evaluation",
            status="waiting_for_user",
            message=message,
            data=data,
            actions=[{"type": "submit_answer"}],
        )

    if a_status == "giving_hint":
        data["hint_level"] = activity.get("hint_level", 0)
        return AgentResponse(
            type="hint",
            status="waiting_for_user",
            message=message,
            data=data,
            actions=[{"type": "submit_answer"}],
        )

    if a_status == "evaluating":
        return AgentResponse(
            type="evaluation",
            status="running",
            message=message,
            data=data,
        )

    if a_status == "completed":
        return AgentResponse(
            type="evaluation",
            status="completed",
            message=message,
            data=data,
        )

    if a_status == "abandoned":
        return AgentResponse(
            type="evaluation",
            status="cancelled",
            message=message,
            data=data,
        )

    # idle / inconnu → texte
    return response_from_text(message, activity)


def response_from_search(
    message: str,
    results: list[dict],
    source_type: str = "web",
) -> AgentResponse:
    """Résultats de search utilisés dans la réponse → AgentResponse
    type=search (§24 : réutilise SearchResult, pas de 2e système).

    Expose UNIQUEMENT title/source/url/snippet (§31 UX search)
    — jamais source_quality ni les scores internes (§32).
    """
    clean = []
    for r in results:
        clean.append(
            {
                "title": r.get("title") or r.get("source", ""),
                "source": r.get("source", ""),
                "url": r.get("url"),
                "snippet": (r.get("snippet") or "")[:200],
            }
        )
    return AgentResponse(
        type="search",
        status="completed",
        message=message,
        data={"results": clean, "result_count": len(clean)},
    )


def response_from_clarification(
    message: str,
    candidates: list[str] | None = None,
    options_label: dict | None = None,
) -> AgentResponse:
    """Clarification (§25) → AgentResponse avec action select.

    Le frontend peut afficher des BOUTONS à partir de
    actions[0].options — sans parser le texte.
    """
    options = [
        (options_label or {}).get(c, c) for c in (candidates or [])
    ]
    actions = []
    if candidates:
        actions.append(
            {"type": "select", "options": options}
        )
    return AgentResponse(
        type="clarification",
        status="waiting_for_user",
        message=message,
        data={"candidates": candidates or []},
        actions=actions,
    )


def response_from_error(
    message: str,
) -> AgentResponse:
    """Erreur utilisateur-visible (§5 ADDENDUM : JAMAIS de stack
    trace/traceback/exception brute/chemin serveur/secret —
    ces détails restent dans les logs)."""
    return AgentResponse(
        type="error",
        status="error",
        message=message,
    )


def normalize_response(
    message: str,
    activity: dict | None = None,
    search_results: list[dict] | None = None,
    search_used: bool = False,
    fallback: FallbackDecision | None = None,
    error: str | None = None,
) -> AgentResponse:
    """POINT D'ENTRÉE du normalizer (§26).

    Priorité de conversion :
      1. error → response_from_error
      2. fallback ask_clarification → clarification (+candidates)
      3. activité en cours → response_from_activity
      4. search utilisé → response_from_search
      5. défaut → response_from_text

    Chaque branche logge la normalisation (observabilité sans
    contenu sensible).
    """
    if error:
        resp = response_from_error(error)
        origin = "error"
    elif fallback and fallback.action == "ask_clarification":
        resp = response_from_clarification(
            message, candidates=fallback.candidates or None
        )
        origin = "clarification"
    elif activity and activity.get("activity_type"):
        resp = response_from_activity(message, activity)
        origin = "activity"
    elif search_used and search_results:
        resp = response_from_search(message, search_results)
        origin = "search"
    else:
        resp = response_from_text(message, activity)
        origin = "text"

    log_event(
        "RESPONSE_NORMALIZED",
        message=(
            f"Response normalized | origin={origin} | "
            f"type={resp.type} | status={resp.status}"
        ),
        extra={
            "operation": "response_normalize",
            "origin": origin,
            "response_type": resp.type,
            "response_status": resp.status,
        },
    )
    return resp
