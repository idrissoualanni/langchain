# SHIM de compatibilité (refactor — phase migration).
#
# Les code tools ont déménagé vers app/tools/coding/.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.tools.coding import (
    MAX_CODE_CHARS,
    _code_tools_enabled,
    analyze_code,
    code_tools,
    execute_code,
    run_python_isolated,
    run_tests,
    static_security_scan,
)

__all__ = [
    "MAX_CODE_CHARS",
    "_code_tools_enabled",
    "analyze_code",
    "code_tools",
    "execute_code",
    "run_python_isolated",
    "run_tests",
    "static_security_scan",
]
