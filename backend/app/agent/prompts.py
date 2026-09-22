# SHIM de compatibilité (refactor — phase migration).
#
# Les prompts ont déménagé vers app/services/agent/prompts.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.services.agent.prompts import CORE_PROMPT, SYSTEM_PROMPT

__all__ = ["CORE_PROMPT", "SYSTEM_PROMPT"]
