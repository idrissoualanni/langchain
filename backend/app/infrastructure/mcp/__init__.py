# Couche MCP (Model Context Protocol) — doc §39-§41.
#
# MCP est une frontière d'intégration :
#
#   MCP Server → MCP Client/Toolset → Workflow / Agent
#
# Architecture (§39) : un registry déclare les serveurs autorisés avec
# leurs capabilities, permissions et workflows cibles. Le toolset (§40)
# charge les tools et les SCOPE par workflow — jamais d'exposition
# globale au Main Agent. La sécurité (§41) : allowlist, timeouts, rate
# limits, audit, failure isolation.
#
# Dépendances : mcp 1.29 (FastMCP), langchain-mcp-adapters 0.3.2
# (MultiServerMCPClient / load_mcp_tools).
from app.infrastructure.mcp.registry import (
    McpRegistry,
    McpServerConfig,
    get_registry,
    list_servers,
)
from app.infrastructure.mcp.toolset import get_mcp_tools, list_mcp_tools_sync

__all__ = [
    "McpRegistry",
    "McpServerConfig",
    "get_registry",
    "list_servers",
    "get_mcp_tools",
    "list_mcp_tools_sync",
]
