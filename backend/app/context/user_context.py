# User Context — sélectionne les informations mémoire pertinentes
# pour UN appel LLM. Ne renvoie jamais tout le store sans filtrage.
from app.agent.memory import FACT_CATEGORIES
from app.logging.events import log_event

# Étiquettes lisibles par catégorie (pour le prompt)
CATEGORY_LABELS = {
    "identity": "Identity",
    "background": "Background",
    "personality": "Personality",
    "preference": "Preferences",
    "interest": "Interests",
}


def build_user_context(
    user_id: str,
    profile: dict,
    relevant_memories: list[dict],
) -> dict:
    """Construit le bloc USER CONTEXT du prompt.

    - Profil v2 : nom (identity.name) + description si présente
    - Faits : uniquement ceux SÉLECTIONNÉS par le Context Builder
      (déjà filtrés par pertinence / quota)

    Retourne {"text": str, "facts_count": int}.
    Émet USER_MEMORY_SELECTED (observabilité §26).
    """
    lines: list[str] = []

    # --- Identity (profil v2) ---
    name = profile.get("name")
    description = profile.get("description")
    if name or description:
        lines.append("Name:")
        lines.append(name or "(non précisé)")
        if description:
            lines.append("")
            lines.append("Description:")
            lines.append(description)
        lines.append("")

    # --- Faits sélectionnés, groupés par catégorie ---
    by_cat: dict[str, list[str]] = {}
    for fact in relevant_memories:
        cat = fact.get("category")
        if cat not in FACT_CATEGORIES:
            continue
        by_cat.setdefault(cat, []).append(fact.get("content", ""))

    for cat in FACT_CATEGORIES:
        contents = by_cat.get(cat)
        if not contents:
            continue
        lines.append(f"{CATEGORY_LABELS.get(cat, cat)}:")
        for c in contents:
            lines.append(f"- {c}")
        lines.append("")

    text = "\n".join(lines).strip()

    log_event(
        "USER_MEMORY_SELECTED",
        message=(
            f"User context | user={user_id} | "
            f"facts={len(relevant_memories)} | "
            f"chars={len(text)}"
        ),
        user_id=user_id,
        extra={
            "operation": "user_context",
            "facts_selected": len(relevant_memories),
            "categories": sorted(by_cat.keys()),
            "chars": len(text),
        },
    )

    return {"text": text, "facts_count": len(relevant_memories)}
