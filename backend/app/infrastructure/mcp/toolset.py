# MCP Toolset (§40/§41) — chargement + scoping des tools MCP.
#
# get_mcp_tools(workflow) résout les serveurs autorisés pour CE
# workflow (registry §39), ouvre les sessions via MultiServerMCPClient
# et convertit les tools MCP en tools LangChain (load_mcp_tools).
#
# Scoping (§40) : un workflow ne reçoit QUE les tools des serveurs dont
# allowed_workflows le contient. Le Main Agent n'en reçoit JAMAIS.
#
# Sécurité (§41) : failure isolation — un serveur défaillant est isolé
# (log + skip), les autres servent quand même ; jamais de crash du run.
from __future__ import annotations

from typing import Any

from app.logging.events import log_event


async def get_mcp_tools(workflow: str) -> list[Any]:
    """Tools LangCHAIN chargés depuis les serveurs MCP d'un workflow.

    Retourne une liste (vide si aucun serveur ou tout échec). La
    fonction est ASYNC : les sessions MCP ne vivent que le temps de
    l'appel — le caller (node) les utilise puis les relâche.
    """
    from app.infrastructure.mcp.registry import get_registry

    registry = get_registry()
    servers = registry.for_workflow(workflow)

    if not servers:
        # Pas une erreur : la plupart des workflows n'ont pas de MCP.
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    connections: dict[str, dict] = {}
    for cfg in servers:
        connections[cfg.name] = {
            "command": cfg.command,
            "args": list(cfg.args),
            "transport": cfg.transport,
        }

    tools: list[Any] = []
    try:
        # API langchain-mcp-adapters >= 0.1.0 : le client n'est PLUS un
        # context manager — get_tools() ouvre/ferme les sessions lui-même.
        client = MultiServerMCPClient(connections)
        for cfg in servers:
            try:
                server_tools = await client.get_tools(
                    server_name=cfg.name
                )
                tools.extend(server_tools)
                log_event(
                    "MCP_TOOLS_LOADED",
                    message=(
                        f"MCP tools loaded | server={cfg.name} "
                        f"| workflow={workflow} "
                        f"| tools={len(server_tools)}"
                    ),
                    extra={
                        "operation": "mcp_toolset",
                        "server": cfg.name,
                        "workflow": workflow,
                        "tool_names": [
                            getattr(t, "name", "") for t in server_tools
                        ],
                    },
                )
            except Exception as exc:
                # §41 failure isolation : un serveur KO n'empêche
                # jamais les autres de servir.
                log_event(
                    "MCP_SERVER_FAILED",
                    level="WARNING",
                    message=(
                        f"MCP server {cfg.name} unavailable : {exc} "
                        f"— isolated, continuing without its tools"
                    ),
                    extra={
                        "operation": "mcp_toolset",
                        "server": cfg.name,
                        "workflow": workflow,
                    },
                )
    except Exception as exc:
        # Échec global du client : on dégrade en mode sans MCP (jamais
        # de crash du run — le workflow reste fonctionnel sans tools).
        log_event(
            "MCP_CLIENT_FAILED",
            level="WARNING",
            message=(
                f"MCP client failed for workflow={workflow} : {exc} "
                f"— continuing without MCP tools"
            ),
            extra={"operation": "mcp_toolset", "workflow": workflow},
        )
        return []

    return tools


def list_mcp_tools_sync(workflow: str) -> list[str]:
    """Helper synchrone d'observabilité : noms des tools attendus.

    Ne lance AUCUNE session — reflete seulement le registry (§39).
    """
    from app.infrastructure.mcp.registry import get_registry

    return [c.name for c in get_registry().for_workflow(workflow)]


__all__ = ["get_mcp_tools", "list_mcp_tools_sync"]
