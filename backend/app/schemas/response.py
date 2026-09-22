# Structured Agent Output V6.7 (§16-§26 + ADDENDUM statuts).
#
# CONTRAT PUBLIC — 5 couches d'état STRICTEMENT séparées :
#
#   1. AgentResponse.status  — état PUBLIC de la réponse
#      (completed / waiting_for_user / running / error / cancelled)
#      — « success » est REFUSÉ par le schéma (ADDENDUM §7 :
#      c'est un statut technique interne, pas conversationnel).
#   2. learning_activity.status — machine à états pédagogique
#      (idle/waiting_for_answer/evaluating/giving_hint/
#      waiting_for_retry/checking_understanding/completed/
#      abandoned) — INCHANGÉ (V5.2).
#   3. SearchResponse.status — retrieval (found/insufficient/
#      unavailable/error) — V6.5, INCHANGÉ.
#   4. RoutingResult.status — routing (supported/ambiguous/
#      unknown/unsupported/multi_domain) — V4/V5, INCHANGÉ.
#   5. FallbackDecision.action — décision de fallback — V6.6.
#
# Exemple de flux (ADDENDUM §9) :
#   SearchResponse.insufficient → FallbackDecision.use_web_search
#   → AgentResponse(type=text, status=completed)
# Chaque couche garde son vocabulaire — aucune n'écrase l'autre.
#
# Déplacé depuis app/agent/response.py (refactor : les contrats
# vivent dans app/schemas/, jamais dans l'orchestration).
from typing import Any, Literal

from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# Statuts publics — ADDENDUM §1 (EXACTEMENT ces 5, pas de success)
# ------------------------------------------------------------------
AgentResponseStatus = Literal[
    "completed",        # réponse terminée, n'attend rien
    "waiting_for_user", # tour fini, intervention étudiant attendue
    "running",          # opération visible en cours (rare §4)
    "error",            # opération impossible (message propre)
    "cancelled",        # interruption volontaire
]

# Types de réponse — §19 (minimum imposé par la mission)
AgentResponseType = Literal[
    "text",           # explication / conversation
    "exercise",       # exercice posé
    "quiz",           # question de quiz
    "evaluation",     # feedback d'évaluation
    "hint",           # indice progressif
    "code",           # activité de code (éditeur)
    "search",         # réponse s'appuyant sur la recherche
    "clarification",  # demande de précision
    "error",          # échec utilisateur-visible
]


class AgentResponse(BaseModel):
    """Réponse structurée de l'agent (contrat frontend §17).

    Stable et versionnable : version transportée pour évolution
    future sans casser les clients existants.

    Le frontend rend cette réponse via response.type — JAMAIS
    en parsant le texte (§18 : interdit if message.includes).
    """

    version: int = Field(
        default=1,
        description="Version du contrat (migration progressive)",
    )
    type: AgentResponseType = Field(
        description="Nature de la réponse — pilote le renderer"
    )
    status: AgentResponseStatus = Field(
        description="État PUBLIC : completed/waiting_for_user/"
        "running/error/cancelled (success interdit — "
        "technique interne)"
    )
    message: str = Field(
        default="",
        description="Texte principal (le LLM reste la voix)",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Charge utile typée par response.type "
        "(§20-§23 : jamais keyword list/hidden answer/"
        "scoring metadata internes)",
    )
    actions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Actions proposées au frontend (§25 : "
        "select avec options, submit_answer, request_hint...)",
    )


__all__ = [
    "AgentResponse",
    "AgentResponseStatus",
    "AgentResponseType",
]
