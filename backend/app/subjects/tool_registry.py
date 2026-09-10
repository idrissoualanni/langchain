# Tool Registry — quels tools pour quelle matière, avec disponibilité RÉELLE.
# Un SubjectConfig DÉCLARE des tools ; le registry distingue
# implémentés (utilisables maintenant) / déclarés (à venir).
from app.logging.events import log_event

# Tools réellement implémentés dans l'agent (couche langchain @tool)
IMPLEMENTED_TOOLS = {
    "additionner",
    "calculer_longueur_texte",
    "recherche_web",
    "get_user_profile",
    "update_user_profile",
    "get_user_memory",
    "save_user_memory",
    "update_user_memory",
    "delete_user_memory",
    "search_user_memory",
    # V4.1 — pédagogiques communs (implémentations réelles,
    # branchées sur la base knowledge)
    "create_exercise",
    "evaluate_answer",
    "give_hint",
}

# Tools pédagogiques communs — désormais IMPLÉMENTÉS (V4.1)
COMMON_PEDAGOGICAL_TOOLS = {
    "create_exercise": "Génère un exercice adapté",
    "evaluate_answer": "Évalue une réponse d'étudiant",
    "give_hint": "Donne un indice sans la solution",
}


def get_tools_for_subject(subject_id: str | None) -> dict:
    """Tools disponibles pour une matière.

    Retourne :
    {
        "available":          [tools implémentés utilisables],
        "declared_common":    [déclarés communs — à venir],
        "declared_specialized": [déclarés spécialisés — à venir],
        "available_count": int,
        "declared_count": int,
    }
    """
    from app.subjects.registry import get_subject

    cfg = get_subject(subject_id) if subject_id else None

    # Base : tools réels de l'agent toujours disponibles
    available = sorted(IMPLEMENTED_TOOLS)
    declared_common: list[str] = []
    declared_specialized: list[str] = []

    if cfg:
        declared_common = [
            t
            for t in cfg.tools.get("common", [])
            if t not in IMPLEMENTED_TOOLS  # implémentés → pas "déclarés"
        ]
        declared_specialized = list(
            cfg.tools.get("specialized", [])
        )

    log_event(
        "TOOLS_SELECTED",
        message=(
            f"Tools selected | subject={subject_id} | "
            f"available={len(available)} | "
            f"declared={len(declared_common) + len(declared_specialized)}"
        ),
        extra={
            "operation": "tools_selected",
            "subject": subject_id or "",
            "tools_available": available,
            "tools_declared": declared_common + declared_specialized,
        },
    )
    return {
        "available": available,
        "declared_common": declared_common,
        "declared_specialized": declared_specialized,
        "available_count": len(available),
        "declared_count": len(declared_common)
        + len(declared_specialized),
    }
