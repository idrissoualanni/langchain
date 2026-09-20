# WORKFLOW_ROUTER — node de routage de workflow du Main Graph (§4/§31).
#
# Le plan distingue ROUTER (de quoi parle la demande ? → matière) de
# WORKFLOW ROUTER (quel WORKFLOW exécuter ? → main / activity /
# problem / coding / research / video / document).
#
# §31 Router V2 : workflow-aware + intent + activity continuation.
# Phase 1 pose le CONTRAT (WorkflowDecision persisté + conditionnel
# câblé) SANS brancher de subgraph (Phases 2-7). Le comportement
# reste donc équivalent : tout workflow non encore implémenté retombe
# sur la chaîne principale ("main") — non-régression garantie.
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.graph.subgraphs.contracts import KNOWN_WORKFLOWS
from app.logging.events import log_event

# Marqueurs DÉTERMINISTES d'une requête de résolution d'énoncé (§21).
# §32 : pas de LLM pour router quand une règle suffit — ces marqueurs
# déclenchent l'intent "solve_problem" (ProblemSubgraph).
_SOLVE_PROBLEM_MARKERS = (
    "résous", "resous", "résolution", "resolution", "calcule", "derive",
    "intégrale", "integrale", "primitive", "équation", "equation", "factorise",
    "développe", "developpe", "résoudre", "resoudre", "énoncé", "enonce",
    "exercice", "fais ce", "problème", "probleme", "montre que", "suit(e)",
)


def _intent_solve_problem(state: dict) -> bool:
    """Détection déterministe d'une demande de résolution (Intent, §32).

    Consomme le query normalisé par INTAKE (ou le dernier message
    humain). L'activité en cours a PRIORITÉ (continuation §16) — si une
    activité attend une réponse, le sous-graphe problem ne doit pas
    concurrencer l'évaluation : c'est la chaîne "activity" qui gagne.
    """
    activity = state.get("learning_activity") or {}
    status = activity.get("status") if isinstance(activity, dict) else ""
    if status in (
        "waiting_for_answer",
        "giving_hint",
        "waiting_for_retry",
        "checking_understanding",
        "evaluating",
    ):
        return False

    intake = state.get("intake") or {}
    query = intake.get("query") if isinstance(intake, dict) else ""
    if not query:
        query = (state or {}).get("query") or ""
    query_l = (query or "").lower()
    return any(marker in query_l for marker in _SOLVE_PROBLEM_MARKERS)


def _capability_gate_reason(workflow: str) -> str | None:
    """Gate de capabilities (§4) — raisons du blocage, None si OK.

    Résout le modèle du purpose du workflow via le RESOLVER (aucun
    LLM, déterministe) et vérifie les capacités requises. Un modèle
    absent/désactivé/sans capacité → raison explicite (le routage
    retombera sur la chaîne principale, documentée).
    """
    requirement = _CAPABILITY_REQUIREMENTS.get(workflow)
    if requirement is None:
        return None

    from app.models.resolver import resolve_model_for_purpose

    result = resolve_model_for_purpose(
        purpose=requirement["purpose"],
        required_capabilities=requirement["capabilities"],
    )
    if result.is_enabled and result.config:
        return None
    return (
        f"workflow='{workflow}' requiert {requirement['capabilities']} "
        f"mais modèle indisponible : {result.reason}"
    )

# Workflows ayant UNE BRANCHE RÉELLE dans le graphe compilé.
# Phase 2 : "activity" est câblé (continuation §16/§17 → node
# ACTIVITY qui confirme le contrat puis revient sur la chaîne
# principale). "main" reste la chaîne principale.
# Phase 3 : "problem" est câblé (ProblemSubgraph §21 → node PROBLEM
# qui exécute la résolution déterministe puis revient sur la chaîne).
# Les subgraphs coding/research/video/document arrivent Phases 4-7
# et étendent ce set.
WIRED_WORKFLOWS: dict[str, str] = {
    "main": "context",
    "activity": "activity",
    "problem": "problem",
}

# Gate de capabilities (mission §4) : un subgraph exigeant une
# capacité (coding/research → tools, video → vision) n'est exécuté
# que si le modèle résolu pour son purpose la supporte. Sinon
# fallback documenté sur la chaîne principale (jamais silencieux).
_CAPABILITY_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "coding": {"purpose": "coding", "capabilities": ["tools"]},
    "research": {"purpose": "research", "capabilities": ["tools"]},
    "video": {"purpose": "vision", "capabilities": ["vision"]},
}


class WorkflowDecision(BaseModel):
    """Décision de routage vers un workflow (§4/§8).

    workflow    : nom du workflow cible (KNOWN_WORKFLOWS)
    reason      : raison lisible de la décision
    attached_to : qualificatif complémentaire si utile
                  (ex: id d'activité pour la continuation)
    """

    model_config = {"extra": "forbid"}

    workflow: str = Field(
        default="main",
        description="Workflow cible (KNOWN_WORKFLOWS)",
    )
    reason: str = Field(
        default="",
        description="Raison lisible de la décision",
    )
    attached_to: str = Field(
        default="",
        description="Identifiant associé (ex: activity_id)",
    )


def decide_workflow(state: dict) -> WorkflowDecision:
    """Décide quel workflow exécuter — PURE (matrice déterministe).

    Consomme l'état courant et produit UNE décision, sans jamais
    appeler de LLM (§3 : service interne). Phase 1 :
      - la chaîne "main" par défaut (routing/knowledge déjà
        résolus par ROUTER/GETRIEVAL/FALLBACK)
      - "activity" si un activité attente de réponse (continuation
        §16) — le WORKFLOW_ROUTER le signale dès maintenant, le
        branchage effectif arrivera Phase 2.
    """
    workflow = "main"
    reason = "Chaîne principale : routage/retrieval fait (Phase 1)"
    attached = ""

    activity = state.get("learning_activity") or {}
    status = activity.get("status") if isinstance(activity, dict) else ""
    if status in (
        "waiting_for_answer",
        "giving_hint",
        "waiting_for_retry",
        "checking_understanding",
        "evaluating",
    ):
        workflow = "activity"
        attached = activity.get("activity_id", "")
        reason = (
            f"Activité en cours (status={status}, "
            f"id={attached}) — continuation (§16)"
        )
    elif _intent_solve_problem(state):
        workflow = "problem"
        reason = (
            "Requête de résolution d'énoncé (intent solve_problem, "
            "marqueurs déterministes) — ProblemSubgraph (§21)"
        )

    return WorkflowDecision(
        workflow=workflow, reason=reason, attached_to=attached
    )


def workflow_router_node(state, config=None) -> dict[str, Any]:
    """WORKFLOW_ROUTER — décide le workflow du run (§4/§31).

    Appel réel : decide_workflow(state) — matrice PURE. Le
    résultat est persisté (canal "workflow", WorkflowDecision dict)
    pour l'observabilité et consommé par route_after_workflow_router.
    """
    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (config.get("configurable") or {}).get(
            "thread_id"
        ) or ""

    decision = decide_workflow(state)

    log_event(
        "WORKFLOW_DECIDED",
        message=(
            f"Workflow decided | workflow={decision.workflow} "
            f"| {decision.reason}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "workflow_router",
            "workflow": decision.workflow,
            "attached_to": decision.attached_to,
        },
    )

    return {"workflow": decision.model_dump()}


def route_after_workflow_router(state) -> str:
    """Conditionnel après WORKFLOW_ROUTER.

    Retourne la DESTINATION du workflow décidé. Les workflows câblés
    (WIRED_WORKFLOWS) ont une branche réelle ; tout workflow non
    implémenté retombe sur "context" (chaîne principale) — la chaîne
    actuelle est préservée à l'identique.

    Gate de capabilities (§4) : avant un subgraph exigent (coding/
    research/video), le modèle résolu pour le purpose doit supporter
    la capacité requise — sinon fallback explicite sur "context"
    (événement WORKFLOW_CAPABILITY_GATE, jamais silencieux).
    """
    decision_dict = (state or {}).get("workflow") or {}
    workflow = decision_dict.get("workflow", "main")
    user_id = (state or {}).get("user_id") or ""

    target = WIRED_WORKFLOWS.get(workflow)
    if target is None:
        log_event(
            "WORKFLOW_UNWIRED",
            message=(
                f"Workflow '{workflow}' not wired yet (Phase 1) — "
                f"falling back to main chain"
            ),
            user_id=user_id,
            extra={"workflow": workflow},
        )
        return "context"

    gate_reason = _capability_gate_reason(workflow)
    if gate_reason:
        log_event(
            "WORKFLOW_CAPABILITY_GATE",
            level="WARNING",
            message=f"Capability gate bloqué : {gate_reason}",
            user_id=user_id,
            extra={"operation": "workflow_router", "workflow": workflow},
        )
        return "context"

    return target


__all__ = [
    "WorkflowDecision",
    "decide_workflow",
    "workflow_router_node",
    "route_after_workflow_router",
    "WIRED_WORKFLOWS",
    "KNOWN_WORKFLOWS",
    "_intent_solve_problem",
    "_capability_gate_reason",
]