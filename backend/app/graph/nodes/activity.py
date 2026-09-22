# ACTIVITY node — continuation d'activité (§16/§17) du Main Graph.
#
# Quand WORKFLOW_ROUTER décide "activity" (une activité attend une
# réponse : status waiting_for_answer / giving_hint / waiting_for_retry
# / checking_understanding / evaluating), CE node :
#
#   1. CONFIRME la continuation (§16) — n'existe jamais de nouvelle
#      activité : on poursuit l'activité du thread.
#   2. Produit le contrat de sortie §8 (ActivityResult) persisté dans
#      workflow_result, pour l'observabilité du Main Graph.
#   3. Retourne vers la chaîne principale (CONTEXT → AGENT) : l'étape
#      d'évaluation/indice réelle reste déléguée aux tools pédagogiques
#      V5.2 (evaluate_answer/give_hint) DANS le sous-graphe agentique —
#      le Main Graph enregistre la continuation, il ne refait pas le
#      travail des tools (standardisation, pas de 2ème évaluation).
#
# Phase 2 : la continuation est câblée comme workflow "activity" réel
# (avant on tombait sur "context" sans branche dédiée).
from __future__ import annotations

from typing import Any

from app.services.activity.continuation import is_active_activity, next_step_hint
from app.schemas.activity import ActivityContract, activity_to_contract
from app.schemas.workflow import ActivityResult
from app.logging.events import log_event


def activity_node(state, config=None) -> dict[str, Any]:
    """ACTIVITY — poursuit l'activité en cours du thread (§16/§17).

    Lit la décision workflow (WorkflowDecision) et l'activité live du
    state, confirme la continuation, et écrit l'ActivityResult dans
    workflow_result (jamais de nouvelle activité, §16).
    """
    activity = {}
    if isinstance(state, dict):
        activity = state.get("learning_activity") or {}
    if not isinstance(activity, dict):
        activity = {}

    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (config.get("configurable") or {}).get(
            "thread_id"
        ) or ""

    workflow_decision = {}
    if isinstance(state, dict):
        workflow_decision = state.get("workflow") or {}
    attached = workflow_decision.get("attached_to", "") if isinstance(
        workflow_decision, dict
    ) else ""
    decision_activity_id = activity.get("activity_id", "") if activity else ""
    activity_id = decision_activity_id or attached or ""

    if not is_active_activity(activity):
        # Défense §16 : le workflow a décidé "activity" mais le state
        # dit plus d'activité active (ex: terminée entre temps) —
        # on ne FORGE pas une activité ; message explicite, on laisse
        # la chaîne principale continuer normalement.
        result = ActivityResult(
            workflow="activity",
            status="pending",
            message=(
                "Workflow activity mais aucune activité active — "
                "continuation ignorée (pas de nouvelle activité)"
            ),
            activity_id=activity_id,
            activity_type=str(
                activity.get("activity_type", "") if activity else ""
            ),
            evaluated=False,
            evaluation={},
        )
        log_event(
            "ACTIVITY_CONTINUATION",
            level="WARNING",
            message="activity workflow without active activity — skipping",
            user_id=user_id,
            thread_id=thread_id,
            extra={"activity_id": activity_id},
        )
        return {"workflow_result": result.model_dump()}

    contract: ActivityContract = activity_to_contract(
        activity, thread_id=thread_id, user_id=user_id
    )
    step = next_step_hint(activity)

    result = ActivityResult(
        workflow="activity",
        status="ok",
        message=(
            f"Continuation activity {activity_id} — étape "
            f"{step['kind']} (status={contract.status})"
        ),
        activity_id=activity_id,
        activity_type=contract.activity_type,
        evaluated=contract.status in ("evaluating", "waiting_for_retry"),
        evaluation=dict(contract.result),
    )

    log_event(
        "ACTIVITY_CONTINUATION",
        message=(
            f"Activity continued | id={activity_id} | "
            f"step={step['kind']} | status={contract.status}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "activity_continuation",
            "activity_id": activity_id,
            "step": step["kind"],
            "status": contract.status,
        },
    )

    return {"workflow_result": result.model_dump()}


def route_after_activity(state) -> str:
    """Après ACTIVITY : retour TOUJOURS sur la chaîne principale.

    La continuation a confirmé le contrat ; l'évaluation/indice se
    joue ensuite dans le sous-graphe agentique (tools V5.2), puis
    RESPONSE — pas de 2ème workflow parallèle (§18 : une seule
    évaluation).
    """
    return "context"


__all__ = ["activity_node", "route_after_activity"]