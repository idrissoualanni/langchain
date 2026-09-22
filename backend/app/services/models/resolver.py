# Model Resolver — Résolution de modèle par purpose (§8-§9)
#
# Le resolver détermine quel modèle utiliser selon :
#   - le purpose (default, coding, research, fast, reasoning, vision)
#   - le scope (user, group, global)
#   - les assignments admin
#   - l'état enabled du modèle
#   - les capacités requises
#
# Priorité de résolution :
#   user-specific > group-specific > global > default
#
# Déterminisme et traçage (mission §2) :
#   - AUCUN LLM dans la résolution
#   - un modèle désactivé n'est JAMAIS sélectionnable
#   - un candidat sans les capacités requises est ignoré
#   - le fallback par défaut est toujours tracé (champ `reason`, et
#     `is_enabled=False` quand AUCUN modèle satisfaisant n'existe)
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from app.services.models.schemas import ModelConfig, ModelAssignment, ModelPurposeResult
from app.services.models.registry import (
    get_model_config,
    list_all_model_configs,
    get_default_model_id,
)

SUPPORTED_PURPOSES: tuple[str, ...] = (
    "default",
    "coding",
    "research",
    "fast",
    "reasoning",
    "vision",
)


# Assignments globaux en mémoire (seront persistés en DB dans une phase suivante)
_global_assignments: dict[str, str] = {}  # purpose -> model_id


def set_global_assignment(purpose: str, model_id: str) -> None:
    """Définit un assignment global pour un purpose."""
    _global_assignments[purpose] = model_id


def get_global_assignment(purpose: str) -> str | None:
    """Récupère l'assignment global pour un purpose."""
    return _global_assignments.get(purpose)


def _usable(config: ModelConfig | None, required_capabilities: list[str] | None) -> bool:
    """Le modèle est-il utilisable (enabled + capacités requises) ?"""
    if config is None or not config.enabled:
        return False
    return _check_capabilities(config, required_capabilities)


def resolve_model_for_purpose(
    purpose: str = "default",
    user_id: str | None = None,
    group_ids: list[str] | None = None,
    required_capabilities: list[str] | None = None,
    path: Path | None = None,
) -> ModelPurposeResult:
    """Résout le modèle à utiliser pour un purpose donné (§8).

    Algorithme de résolution (déterministe, aucun LLM) :
      1. Assignment user-specific si user_id fourni
      2. Assignment group-specific si group_ids fournis
      3. Assignment global
      4. Fallback : env <PURPOSE>_MODEL_ID puis modèle default

    Vérifications à CHAQUE candidat :
      - doit exister dans le registry
      - doit être enabled (un modèle désactivé n'est JAMAIS choisi)
      - doit avoir les capacités requises
      - le fallback est TRACÉ (reason) ; si aucun modèle satisfaisant
        n'existe → is_enabled=False + reason explicite (jamais de
        config bidon silencieuse).
    """
    # 1. Assignment user-specific (priorité max)
    if user_id:
        user_assignment = _get_user_assignment(user_id, purpose)
        if user_assignment:
            config = get_model_config(user_assignment.model_id, path=path)
            if _usable(config, required_capabilities):
                return ModelPurposeResult(
                    model_id=config.id,
                    config=config,
                    resolved_from="user",
                    is_enabled=True,
                    reason=f"User assignment for {purpose}",
                )

    # 2. Assignment group-specific
    if group_ids:
        for group_id in group_ids:
            group_assignment = _get_group_assignment(group_id, purpose)
            if group_assignment:
                config = get_model_config(group_assignment.model_id, path=path)
                if _usable(config, required_capabilities):
                    return ModelPurposeResult(
                        model_id=config.id,
                        config=config,
                        resolved_from="group",
                        is_enabled=True,
                        reason=f"Group {group_id} assignment for {purpose}",
                    )

    # 3. Assignment global
    global_model_id = get_global_assignment(purpose)
    if global_model_id:
        config = get_model_config(global_model_id, path=path)
        if _usable(config, required_capabilities):
            return ModelPurposeResult(
                model_id=config.id,
                config=config,
                resolved_from="global",
                is_enabled=True,
                reason=f"Global assignment for {purpose}",
            )

    # 4. Fallback : env <PURPOSE>_MODEL_ID puis modèle default
    if purpose in SUPPORTED_PURPOSES:
        env_var = f"{purpose.upper()}_MODEL_ID"
    else:
        env_var = ""
    fallback_id = os.getenv(env_var) or get_default_model_id(path=path)

    if not fallback_id:
        return ModelPurposeResult(
            model_id="",
            config=None,
            resolved_from="fallback",
            is_enabled=False,
            reason=(
                f"Aucun modèle défaut configuré pour purpose='{purpose}' "
                f"(registry vide ou 'default' désactivé)"
            ),
        )

    config = get_model_config(fallback_id, path=path)
    if config is None:
        return ModelPurposeResult(
            model_id=fallback_id,
            config=None,
            resolved_from="fallback",
            is_enabled=False,
            reason=(
                f"Modèle '{fallback_id}' introuvable dans le registry "
                f"pour purpose='{purpose}'"
            ),
        )

    if not config.enabled:
        return ModelPurposeResult(
            model_id=config.id,
            config=config,
            resolved_from="fallback",
            is_enabled=False,
            reason=(
                f"Modèle défaut '{config.id}' désactivé (enabled=false) "
                f"— non sélectionnable pour purpose='{purpose}'"
            ),
        )

    if not _check_capabilities(config, required_capabilities):
        return ModelPurposeResult(
            model_id=config.id,
            config=config,
            resolved_from="fallback",
            is_enabled=False,
            reason=(
                f"Modèle défaut '{config.id}' sans capacités requises "
                f"{required_capabilities} pour purpose='{purpose}'"
            ),
        )

    return ModelPurposeResult(
        model_id=config.id,
        config=config,
        resolved_from="fallback",
        is_enabled=True,
        reason=f"Fallback to {config.id} for {purpose}",
    )


def _get_user_assignment(user_id: str, purpose: str) -> ModelAssignment | None:
    """Récupère un assignment user-specific (stub — sera DB)."""
    # TODO: Implémenter depuis DB app.db.model_assignments
    return None


def _get_group_assignment(group_id: str, purpose: str) -> ModelAssignment | None:
    """Récupère un assignment group-specific (stub — sera DB)."""
    # TODO: Implémenter depuis DB app.db.group_model_assignments
    return None


def _check_capabilities(
    config: ModelConfig,
    required_capabilities: list[str] | None,
) -> bool:
    """Vérifie que le modèle a les capacités requises."""
    if not required_capabilities:
        return True

    caps = config.capabilities

    for cap in required_capabilities:
        cap_lower = cap.lower()
        if cap_lower == "tools" and not caps.supports_tools:
            return False
        if cap_lower == "structured_output" and not caps.supports_structured_output:
            return False
        if cap_lower == "vision" and not caps.supports_vision:
            return False
        if cap_lower == "audio" and not caps.supports_audio:
            return False

    return True


def get_model_for_subgraph(
    subgraph_name: str,
    user_id: str | None = None,
    path: Path | None = None,
) -> ModelPurposeResult:
    """Résout le modèle pour un subgraph donné.

    Mapping subgraph -> purpose :
      - coding_subgraph → coding
      - research_subgraph → research
      - problem_subgraph → reasoning
      - activity_subgraph → default
      - video_subgraph → vision
      - document_subgraph → default
      - autres → default
    """
    purpose_map = {
        "coding": "coding",
        "research": "research",
        "problem": "reasoning",
        "activity": "default",
        "video": "vision",
        "document": "default",
    }

    purpose = "default"
    for key, p in purpose_map.items():
        if key in subgraph_name.lower():
            purpose = p
            break

    if purpose != "default":
        required = _CAPABILITIES_FOR_PURPOSE.get(purpose)
    else:
        required = None

    return resolve_model_for_purpose(
        purpose=purpose,
        user_id=user_id,
        required_capabilities=required,
        path=path,
    )


# Capacités requises par purpose (gate §4) — utilisé par le workflow
# router pour les subgraphs coding/research/video.
_CAPABILITIES_FOR_PURPOSE: dict[str, list[str]] = {
    "coding": ["tools"],
    "research": ["tools"],
    "vision": ["vision"],
}


def required_capabilities_for_purpose(purpose: str) -> list[str] | None:
    """Capacités requises pour un purpose (None = aucune exigence)."""
    return _CAPABILITIES_FOR_PURPOSE.get(purpose)


__all__ = [
    "SUPPORTED_PURPOSES",
    "resolve_model_for_purpose",
    "get_model_for_subgraph",
    "set_global_assignment",
    "get_global_assignment",
    "required_capabilities_for_purpose",
]
