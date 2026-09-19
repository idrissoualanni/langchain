# INTAKE — node d'entrée du Main Graph (§4).
#
# Rôle : normaliser l'entrée d'UN run AVANT le ROUTER. Il ne fait
# aucun traitement métier — il GARANTIT les invariants d'entrée :
#   1. query : dernier message humain extrait (jamais de message
#      vide acceptable pour un run utilisateur)
#   2. user_id/thread_id : disponibles (état ou config)
#   3. interaction_count : incrémenté UNE fois par run (au lieu du
#      runner) — le node parent compte, le runner garde le streaming.
#
# Node = étape d'orchestration MINCE : l'extraction du dernier
# message humain est un service interne (persisté en dict, §48).
#
# Phase 1 : INTAKE est câblé entre START et ROUTER. En non-régression,
# s'il échoue, le run continue avec les valeurs par défaut (jamais
# de crash de l'orchestration).
from __future__ import annotations

from typing import Any

from app.graph.state import MainState
from app.logging.events import log_event


def _last_human_query(state: dict) -> str:
    """Dernier message humain du state (contenu str)."""
    from langchain_core.messages import HumanMessage

    for m in reversed(state.get("messages") or []):
        if isinstance(m, HumanMessage):
            content = getattr(m, "content", "")
            if isinstance(content, str):
                return content
            return str(content)
    return ""


def _thread_id(config) -> str:
    if not config:
        return ""
    return (config.get("configurable") or {}).get("thread_id") or ""


def intake_node(state: MainState, config=None) -> dict[str, Any]:
    """INTAKE — normalise l'entrée d'un run (§4).

    Appel réel : aucun service métier (§48) — uniquement des
    invariants. Lit l'état courant (messages, user_id,
    interaction_count), produit le dict d'entrée normalisé
    : {"intake": {...}}.

    Contrat node : (state, config) → dict de canaux à écrire.
    Retourne intake (dict sérialisable) — défensif : une query
    vide est journalisée, pas une erreur.
    """
    query = _last_human_query(state)
    user_id = (state or {}).get("user_id") or ""
    interaction_count = int((state or {}).get("interaction_count") or 0)
    thread_id = _thread_id(config)

    if not query:
        log_event(
            "INTAKE_EMPTY",
            message=(
                "Intake: no human message found in state — "
                "continuing with empty query"
            ),
            user_id=user_id,
            thread_id=thread_id,
        )

    log_event(
        "INTAKE_READY",
        message=(
            f"Intake ready | query chars={len(query)} "
            f"| interaction={interaction_count}"
        ),
        user_id=user_id,
        thread_id=thread_id,
    )

    return {
        "intake": {
            "query": query,
            "user_id": user_id,
            "thread_id": thread_id,
            "interaction_count": interaction_count,
        }
    }