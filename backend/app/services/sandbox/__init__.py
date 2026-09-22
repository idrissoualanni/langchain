# SHIM de compatibilité (refactor — phase migration).
#
# Le sandbox a déménagé vers app/infrastructure/sandbox/.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.infrastructure.sandbox import (
    CodeExecutionRequest,
    CodeExecutionResult,
    SandboxConfig,
    SecureSandbox,
    execute_code,
    get_sandbox,
)

__all__ = [
    "SecureSandbox",
    "SandboxConfig",
    "CodeExecutionRequest",
    "CodeExecutionResult",
    "get_sandbox",
    "execute_code",
]
