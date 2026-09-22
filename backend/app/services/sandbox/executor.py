# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.sandbox.executor import (
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
