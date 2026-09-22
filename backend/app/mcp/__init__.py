# SHIM de compatibilité (refactor — phase migration).
#
# MCP a déménagé vers app/infrastructure/mcp/.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.infrastructure.mcp import (
    McpServerConfig,
    get_mcp_tools,
    get_registry,
    list_servers,
)

__all__ = [
    "McpServerConfig",
    "get_registry",
    "list_servers",
    "get_mcp_tools",
]
