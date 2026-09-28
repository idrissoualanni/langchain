# Cohérence tool_descriptions.py ↔ all_tools ↔ schéma AgentResponse.
#
# Garantit que :
# 1. chaque tool enregistré dans all_tools a EXACTEMENT une description ;
# 2. chaque nom de description correspond à un tool réel (pas d'entrée
#    morte) ;
# 3. chaque response_type cité existe dans le Literal AgentResponseType
#    du contrat public (schemas/response.py) ;
# 4. CORE_PROMPT contient bien le catalogue injecté (aucun {TOOL_CATALOG}
#    résiduel et chaque tool mentionné).
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.response import AgentResponseType  # noqa: E402
from app.services.agent.prompts import CORE_PROMPT  # noqa: E402
from app.services.agent.tool_descriptions import (  # noqa: E402
    TOOL_DESCRIPTIONS,
    build_tool_catalog,
)
from app.tools import all_tools  # noqa: E402


def run() -> int:
    failures = []

    real_names = {t.name for t in all_tools}
    desc_names = [td.name for td in TOOL_DESCRIPTIONS]

    # 1. couverture totale
    missing = real_names - set(desc_names)
    if missing:
        failures.append(f"tools sans description: {sorted(missing)}")

    # 2. pas d'entrée morte / doublon
    ghost = set(desc_names) - real_names
    if ghost:
        failures.append(f"descriptions de tools inexistants: {sorted(ghost)}")
    if len(desc_names) != len(set(desc_names)):
        dupes = {n for n in desc_names if desc_names.count(n) > 1}
        failures.append(f"descriptions en double: {sorted(dupes)}")

    # 3. types valides contre le contrat public
    from typing import get_args

    allowed = set(get_args(AgentResponseType))
    bad_types = {td.response_type for td in TOOL_DESCRIPTIONS} - allowed
    if bad_types:
        failures.append(f"response_type hors contrat: {sorted(bad_types)}")

    # 4. injection dans le prompt
    if "{TOOL_CATALOG}" in CORE_PROMPT:
        failures.append("placeholder {TOOL_CATALOG} non injecté")
    catalog = build_tool_catalog()
    not_in_prompt = [n for n in real_names if n not in CORE_PROMPT]
    if not_in_prompt:
        failures.append(f"tools absents du prompt final: {sorted(not_in_prompt)}")
    if "carte: diagram" not in catalog:
        failures.append("le catalogue ne référence pas la carte diagram")

    total = len(all_tools)
    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        print(f"TOTAL {len(TOOL_DESCRIPTIONS)} descriptions | FAIL {len(failures)}")
        return 1
    print(
        f"[PASS] {total} tools enregistrés = {len(TOOL_DESCRIPTIONS)} descriptions, "
        f"types ∈ contrat, catalogue injecté dans CORE_PROMPT "
        f"({len(CORE_PROMPT)} chars)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
