# MCP Registry (§39) — registry des serveurs MCP autorisés.
#
# Déclare, pour chaque serveur : la connexion (transport stdio),
# les capabilities offertes, les permissions, les workflows autorisés
# à consommer ses tools (scoping §40), et les bornes de sécurité
# (timeouts, rate limits — §41).
#
# Source de vérité : déclaration statique CI-DESSOUS, surchargeable par
# env (MCP_ENABLED_SERVERS) — un serveur non listé ici n'est JAMAIS
# contacté (allowlist, §41).
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.logging.events import log_event

# --- Déclaration des serveurs (§39) --------------------------------
# Serveur agenda : tools calendrier (check_availability, create_event,
# list_events). Exposé au workflow "document" (Calendar workflow §40).

_here = Path(__file__).resolve().parent


class McpServerConfig(BaseModel):
    """Configuration d'un serveur MCP autorisé (§39/§41)."""

    model_config = {"extra": "forbid"}

    name: str = Field(description="Identifiant unique du serveur")
    command: str = Field(description="Commande de lancement (stdio)")
    args: list[str] = Field(
        default_factory=list,
        description="Arguments de la commande",
    )
    transport: Literal["stdio"] = Field(
        default="stdio",
        description="Transport MCP (stdio seul supporté ici)",
    )
    enabled: bool = Field(default=True, description="Serveur actif ?")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Capabilities offertes (ex: calendar, search)",
    )
    allowed_workflows: list[str] = Field(
        default_factory=list,
        description="Workflows autorisés à consommer les tools (§40)",
    )
    timeout_s: float = Field(
        default=30.0,
        description="Timeout d'un appel de tool (§41)",
    )
    rate_limit: int | None = Field(
        default=None,
        description="Appels max par run (§41) ; None = illimité",
    )


def _server_scripts_dir() -> Path:
    return _here / "servers"


def _default_servers() -> dict[str, McpServerConfig]:
    """Serveurs actifs par défaut (§39 allowlist).

    Le serveur agenda est lancé en stdio avec l'interpréteur courant ;
    le chemin du script est absolu (résolu à l'import, pas au runtime).
    """
    import sys

    scripts = _server_scripts_dir()
    agenda_script = scripts / "calendar_server.py"
    fs_script = scripts / "filesystem_server.py"
    return {
        "agenda": McpServerConfig(
            name="agenda",
            command=sys.executable,
            args=[str(agenda_script)],
            transport="stdio",
            enabled=True,
            capabilities=["calendar"],
            # §40 : Calendar workflow → calendar MCP tools. Le workflow
            # "document" porte l'agenda (contrat générique §30).
            allowed_workflows=["document"],
            timeout_s=20.0,
            rate_limit=10,
        ),
        "filesystem": McpServerConfig(
            name="filesystem",
            command=sys.executable,
            args=[str(fs_script)],
            transport="stdio",
            enabled=True,
            capabilities=["filesystem", "file-write"],
            # §40 : création/écriture de fichiers exposée aux workflows
            # document (livrables pédagogiques) et coding (sorties de
            # sandbox). JAMAIS au Main Agent global (scoping strict).
            allowed_workflows=["document", "coding"],
            timeout_s=20.0,
            rate_limit=20,
        ),
    }


def _enabled_from_env() -> set[str] | None:
    """Surcharge env : MCP_ENABLED_SERVERS=agenda,other.

    None = pas de surcharge (defaults). Un set vide = tout désactivé.
    """
    raw = os.getenv("MCP_ENABLED_SERVERS")
    if raw is None:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


class McpRegistry:
    """Registry des serveurs MCP (§39) — allowlist statique + env."""

    def __init__(self, servers: dict[str, McpServerConfig] | None = None):
        self._servers: dict[str, McpServerConfig] = dict(
            servers if servers is not None else _default_servers()
        )
        override = _enabled_from_env()
        if override is not None:
            for cfg in self._servers.values():
                cfg.enabled = cfg.name in override

    def list(self) -> list[McpServerConfig]:
        """Serveurs déclarés (y compris désactivés — observabilité)."""
        return list(self._servers.values())

    def enabled(self) -> list[McpServerConfig]:
        """Serveurs actifs seulement."""
        return [c for c in self._servers.values() if c.enabled]

    def for_workflow(self, workflow: str) -> list[McpServerConfig]:
        """Serveurs actifs autorisés pour CE workflow (scoping §40).

        Un serveur n'est exposé qu'aux workflows explicitement listés
        dans allowed_workflows — jamais au Main Agent globally.
        """
        return [
            cfg
            for cfg in self.enabled()
            if workflow in cfg.allowed_workflows
        ]

    def get(self, name: str) -> McpServerConfig | None:
        return self._servers.get(name)


_registry: McpRegistry | None = None


def get_registry() -> McpRegistry:
    """Singleton du registry (résolu une fois au premier appel)."""
    global _registry
    if _registry is None:
        _registry = McpRegistry()
        log_event(
            "MCP_REGISTRY_INIT",
            message=(
                f"MCP registry | servers={len(_registry.list())} "
                f"| enabled={len(_registry.enabled())}"
            ),
            extra={
                "operation": "mcp_registry",
                "servers": [c.name for c in _registry.list()],
                "enabled": [c.name for c in _registry.enabled()],
            },
        )
    return _registry


def list_servers() -> list[McpServerConfig]:
    """Raccourci : serveurs déclarés."""
    return get_registry().list()


__all__ = [
    "McpServerConfig",
    "McpRegistry",
    "get_registry",
    "list_servers",
]
