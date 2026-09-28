# Cohérence tool_descriptions.py ↔ all_tools ↔ schéma AgentResponse.
#
# Garantit que :
# 1. chaque tool enregistré dans all_tools a EXACTEMENT une description ;
# 2. chaque nom de description correspond à un tool réel (pas d'entrée
#    morte) et qu'il n'y a ni doublon de description ni doublon de tool ;
# 3. chaque response_type cité existe dans le Literal AgentResponseType
#    du contrat public (schemas/response.py) ;
# 4. CORE_PROMPT contient bien le catalogue injecté (aucun {TOOL_CATALOG}
#    résiduel et chaque tool mentionné).
#
# Porté du commit qwen.ai[bot] 864f094, adapté en style pytest.
from typing import get_args

from app.schemas.response import AgentResponseType
from app.services.agent.prompts import CORE_PROMPT
from app.services.agent.tool_descriptions import (
    TOOL_DESCRIPTIONS,
    build_tool_catalog,
)
from app.tools import all_tools


def _real_names() -> set[str]:
    return {t.name for t in all_tools}


def test_tous_les_tools_ont_une_description() -> None:
    missing = _real_names() - {td.name for td in TOOL_DESCRIPTIONS}
    assert not missing, f"tools sans description: {sorted(missing)}"


def test_pas_de_description_morte_ni_double() -> None:
    real = _real_names()
    desc_names = [td.name for td in TOOL_DESCRIPTIONS]

    ghost = set(desc_names) - real
    assert not ghost, f"descriptions de tools inexistants: {sorted(ghost)}"

    dupes = {n for n in desc_names if desc_names.count(n) > 1}
    assert not dupes, f"descriptions en double: {sorted(dupes)}"

    # all_tools ne doit pas non plus porter de doublon (binding LLM)
    tool_names = [t.name for t in all_tools]
    tool_dupes = {n for n in tool_names if tool_names.count(n) > 1}
    assert not tool_dupes, f"tools en double dans all_tools: {sorted(tool_dupes)}"


def test_response_types_dans_le_contrat() -> None:
    allowed = set(get_args(AgentResponseType))
    bad = {td.response_type for td in TOOL_DESCRIPTIONS} - allowed
    assert not bad, f"response_type hors contrat: {sorted(bad)}"


def test_catalogue_injecte_dans_core_prompt() -> None:
    assert "{TOOL_CATALOG}" not in CORE_PROMPT, (
        "placeholder {TOOL_CATALOG} non injecté"
    )
    not_in_prompt = [n for n in _real_names() if n not in CORE_PROMPT]
    assert not not_in_prompt, (
        f"tools absents du prompt final: {sorted(not_in_prompt)}"
    )
    assert "carte: diagram" in build_tool_catalog(), (
        "le catalogue ne référence pas la carte diagram"
    )
