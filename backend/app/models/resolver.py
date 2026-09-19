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
#   user-specific > group-specific > global default > fallback
from __future__ import annotations

import os
from typing import Literal

from app.models.schemas import ModelConfig, ModelAssignment, ModelPurposeResult
from app.models.registry import (
    get_model_config,
    list_all_model_configs,
    get_default_model_id,
)


# Assignments globaux en mémoire (seront persistés en DB dans une phase suivante)
_global_assignments: dict[str, str] = {}  # purpose -> model_id


def set_global_assignment(purpose: str, model_id: str) -> None:
    """Définit un assignment global pour un purpose."""
    _global_assignments[purpose] = model_id


def get_global_assignment(purpose: str) -> str | None:
    """Récupère l'assignment global pour un purpose."""
    return _global_assignments.get(purpose)


def resolve_model_for_purpose(
    purpose: str = "default",
    user_id: str | None = None,
    group_ids: list[str] | None = None,
    required_capabilities: list[str] | None = None,
) -> ModelPurposeResult:
    """Résout le modèle à utiliser pour un purpose donné (§8).
    
    Algorithme de résolution :
      1. Chercher assignment user-specific si user_id fourni
      2. Chercher assignment group-specific si group_ids fournis
      3. Chercher assignment global
      4. Fallback sur le modèle default
    
    Vérifications :
      - Le modèle doit être enabled
      - Le modèle doit avoir les capacités requises si spécifiées
    """
    
    # 1. Assignment user-specific (priorité max)
    if user_id:
        user_assignment = _get_user_assignment(user_id, purpose)
        if user_assignment:
            config = get_model_config(user_assignment.model_id)
            if config and config.enabled:
                if _check_capabilities(config, required_capabilities):
                    return ModelPurposeResult(
                        model_id=config.id,
                        model_config=config,
                        resolved_from="user",
                        is_enabled=True,
                        reason=f"User assignment for {purpose}",
                    )
    
    # 2. Assignment group-specific
    if group_ids:
        for group_id in group_ids:
            group_assignment = _get_group_assignment(group_id, purpose)
            if group_assignment:
                config = get_model_config(group_assignment.model_id)
                if config and config.enabled:
                    if _check_capabilities(config, required_capabilities):
                        return ModelPurposeResult(
                            model_id=config.id,
                            model_config=config,
                            resolved_from="group",
                            is_enabled=True,
                            reason=f"Group {group_id} assignment for {purpose}",
                        )
    
    # 3. Assignment global
    global_model_id = get_global_assignment(purpose)
    if global_model_id:
        config = get_model_config(global_model_id)
        if config and config.enabled:
            if _check_capabilities(config, required_capabilities):
                return ModelPurposeResult(
                    model_id=config.id,
                    model_config=config,
                    resolved_from="global",
                    is_enabled=True,
                    reason=f"Global assignment for {purpose}",
                )
    
    # 4. Fallback : modèle par purpose depuis env ou default
    env_var = f"{purpose.upper()}_MODEL_ID"
    fallback_id = os.getenv(env_var) or get_default_model_id()
    
    config = get_model_config(fallback_id)
    if not config:
        # Créer une config minimale pour le fallback
        config = ModelConfig(id=fallback_id, enabled=True)
    
    is_enabled = config.enabled
    can_use = _check_capabilities(config, required_capabilities)
    
    return ModelPurposeResult(
        model_id=config.id,
        model_config=config,
        resolved_from="fallback",
        is_enabled=is_enabled,
        reason=f"Fallback to {fallback_id} for {purpose}" + (
            "" if can_use else " (capabilities mismatch)"
        ),
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
    
    return resolve_model_for_purpose(purpose=purpose, user_id=user_id)


__all__ = [
    "resolve_model_for_purpose",
    "get_model_for_subgraph",
    "set_global_assignment",
    "get_global_assignment",
]
