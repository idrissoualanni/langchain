# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.mcp.registry import (
    McpServerConfig,
    get_registry,
    list_servers,
)

__all__ = ["McpServerConfig", "get_registry", "list_servers"]
