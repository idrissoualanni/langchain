# Tool Registry V5 — résolution des tools réellement disponibles (§28/§39).
#
# Source de vérité UNIQUE (§29) :
#   - les tools IMPLÉMENTÉS sont déclarés ici, référencés par
#     app/agent/tools.py (all_tools) — une seule liste
#   - les SubjectConfig DÉCLARENT des tools (common/specialized) mais
#     ne les créent pas (§27)
#   - resolve_tools() croise déclaré × implémenté :
#       available   → exposés au modèle
#       unavailable → déclarés mais non enregistrés : LOGGÉS (§39),
#                     jamais exposés, jamais prétendus fonctionnels
from app.logging.events import log_event


def _implemented_tool_names() -> set[str]:
    """Noms des tools réellement enregistrés dans l'agent.

    Import tardif : évite le cycle tools.py → memory.py ↔ registry.
    La liste vient de app.agent.tools.all_tools (source unique).
    """
    from app.agent.tools import all_tools

    return {t.name for t in all_tools}


def resolve_tools(
    declared: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Croise les tools déclarés avec les tools enregistrés.

    Retourne (available, unavailable) :
      available   = déclarés ET implémentés (exposables)
      unavailable = déclarés mais ABSENTS de l'agent (§39 : logger,
                    ne pas exposer, continuer)

    Exemple (§53) : un SubjectConfig déclare execute_python alors
    que le tool n'existe pas → execute_python finit dans
    unavailable avec un log WARNING, jamais dans le prompt.
    """
    implemented = _implemented_tool_names()
    declared = declared or []
    available = [t for t in declared if t in implemented]
    unavailable = [t for t in declared if t not in implemented]

    for missing in unavailable:
        log_event(
            "TOOL_UNAVAILABLE",
            level="WARNING",
            message=(
                f"SubjectConfig declares tool '{missing}' but it is "
                "not registered in the agent — not exposed to the "
                "model"
            ),
            extra={
                "operation": "tool_resolution",
                "tool": missing,
            },
        )
    return available, unavailable


def resolve_tools_for_subject(
    subject_id: str | None,
) -> tuple[list[str], list[str]]:
    """resolve_tools appliqué à un SubjectConfig (common+specialized)."""
    from app.subjects.registry import get_subject

    cfg = get_subject(subject_id) if subject_id else None
    if cfg is None:
        return [], []
    declared = list(cfg.tools.get("common", [])) + list(
        cfg.tools.get("specialized", [])
    )
    return resolve_tools(declared)


def get_tools_for_subject(subject_id: str | None) -> dict:
    """API de compatibilité (frontend/preview) : dict de stats.

    available = TOUS les tools implémentés de l'agent (le modèle
    les reçoit tous via create_agent) ; declared_common/
    declared_specialized = ce que le SubjectConfig déclare.
    """
    from app.subjects.registry import get_subject

    implemented = sorted(_implemented_tool_names())
    cfg = get_subject(subject_id) if subject_id else None

    declared_common: list[str] = []
    declared_specialized: list[str] = []
    if cfg:
        declared_common = [
            t
            for t in cfg.tools.get("common", [])
            if t not in implemented  # implémentés → pas « à venir »
        ]
        declared_specialized = [
            t
            for t in cfg.tools.get("specialized", [])
            if t not in implemented
        ]

    log_event(
        "TOOLS_SELECTED",
        message=(
            f"Tools selected | subject={subject_id} | "
            f"available={len(implemented)} | "
            f"declared={len(declared_common) + len(declared_specialized)}"
        ),
        extra={
            "operation": "tools_selected",
            "subject": subject_id or "",
            "tools_available": implemented,
            "tools_declared": declared_common + declared_specialized,
        },
    )
    return {
        "available": implemented,
        "declared_common": declared_common,
        "declared_specialized": declared_specialized,
        "available_count": len(implemented),
        "declared_count": len(declared_common)
        + len(declared_specialized),
    }
