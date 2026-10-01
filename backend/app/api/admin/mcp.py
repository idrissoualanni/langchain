"""Inspecteur MCP — API d'administration des serveurs MCP (§39/§40/§41).

PRINCIPE (voie A, arretee) : le navigateur ne parle JAMAIS le protocole
MCP. Il parle REST a cette API, qui pilote les serveurs **stdio**
existants via `app.infrastructure.mcp.session`. Un pipe de processus
n'est pas adressable depuis une page web — et surtout, exposer du
stdio en HTTP obligerait a transporter l'identite utilisateur par
header de requete, ce qui rouvrait la faille §41.

Ce que cette API REUTILISE tel quel, sans le modifier :
  - `registry.py`   : allowlist des serveurs (§39), scoping par
                      workflow (§40), timeouts et rate-limits.
  - les 2 serveurs  : toute leur validation de chemin/taille (§41)
                      s'applique, car on passe par leur interface
                      `tools/` et jamais par leur code interne.

Identite : `current_user.user_id` (UUID interne), resolu par
`require_admin`. JAMAIS un `user_id` venant du corps de requete —
sinon un admin pourrait ecrire dans l'espace d'un autre utilisateur.

Rate-limit : application du `rate_limit` du registre (fenetre
glissante par couple serveur/utilisateur). C'est une garde de
confort pour l'UI ; la limite de debit reelle reste le role admin.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from mcp.shared.exceptions import McpError
from pydantic import BaseModel, Field

from app.auth.resolver import CurrentUser, require_admin
from app.infrastructure.mcp.registry import McpServerConfig, get_registry
from app.infrastructure.mcp.session import get_pool
from app.logging.events import log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["admin-mcp"])


def verify_admin_auth(current_user: CurrentUser = Depends(require_admin)) -> CurrentUser:
    """Garde d'administration, alignee sur les autres routers /api/admin."""
    return current_user


# ---------------------------------------------------------------------------
# Rate-limit (fenetre glissante)
# ---------------------------------------------------------------------------

# (server_name, user_id) -> horodatages des appels dans la fenetre.
_rate_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_RATE_WINDOW_S = 60.0


def _check_rate_limit(cfg: McpServerConfig, user_id: str) -> None:
    """Applique `cfg.rate_limit` (None = illimite). Lève 429 si dépassé."""
    limit = cfg.rate_limit
    if not limit or limit <= 0:
        return
    now = time.monotonic()
    key = (cfg.name, user_id or "-")
    hits = _rate_hits[key]
    # Purge des appels hors fenetre.
    while hits and (now - hits[0]) > _RATE_WINDOW_S:
        hits.popleft()
    if len(hits) >= limit:
        retry_after = max(1.0, _RATE_WINDOW_S - (now - hits[0]))
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate-limit MCP atteint pour '{cfg.name}' "
                f"({limit} appels / {_RATE_WINDOW_S:.0f}s). "
                f"Reessayez dans {retry_after:.0f}s."
            ),
        )
    hits.append(now)


def reset_rate_limits() -> None:
    """Vide les compteurs (tests / changement de config en dev)."""
    _rate_hits.clear()


# ---------------------------------------------------------------------------
# Resolution d'un serveur
# ---------------------------------------------------------------------------


def _resolve_server(name: str) -> McpServerConfig:
    """Retourne un serveur DECLARE dans le registre (§39).

    404 si inconnu, 409 si desactive : on ne peut ni inventer un
    serveur, ni lancer un sous-processus dont l'admin a coupe l'acces
    dans le registre.
    """
    cfg = get_registry().get(name)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Serveur MCP inconnu : '{name}'. "
                f"Declare : {[c.name for c in get_registry().list()]}"
            ),
        )
    if not cfg.enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Serveur MCP '{name}' desactive dans le registre "
                f"(MCP_ENABLED_SERVERS le filtre). Reactivation requise."
            ),
        )
    return cfg


def _serialize_content(blocks: Any) -> list[dict[str, Any]]:
    """Aplatit les blocs de contenu MCP en JSON affichable.

    On privilegie `text` ; un bloc non textuel (image, resource) est
    rendu via `repr` plutot que perdu, pour que l'inspector montre
    qu'il y a eu quelque chose sans ecrire de gros blobs en base.
    """
    out: list[dict[str, Any]] = []
    for block in blocks or []:
        kind = getattr(block, "type", None) or type(block).__name__
        text = getattr(block, "text", None)
        if text is not None:
            out.append({"type": kind, "text": str(text)})
        else:
            out.append({"type": kind, "repr": repr(block)[:2000]})
    return out


# ---------------------------------------------------------------------------
# Schemas de reponse
# ---------------------------------------------------------------------------


class McpServerOut(BaseModel):
    name: str = Field(description="Nom logique du serveur (cle d'allowlist)")
    transport: str = Field(description="Transport MCP — 'stdio' pour tous ici")
    enabled: bool = Field(description="Active dans le registre ?")
    capabilities: list[str] = Field(default_factory=list)
    allowed_workflows: list[str] = Field(
        default_factory=list, description="Workflows autorises (§40)"
    )
    timeout_s: float = Field(description="Timeout declare du serveur")
    rate_limit: int | None = Field(default=None, description="Appels / minute")
    description: str = ""


class McpToolOut(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema des arguments d'entree"
    )
    output_schema: dict[str, Any] | None = None


class McpToolsOut(BaseModel):
    server: str
    tools: list[McpToolOut] = Field(default_factory=list)
    duration_ms: int = 0


class McpInvokeIn(BaseModel):
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments de l'appel, conformes au JSON Schema du tool",
    )


class McpInvokeOut(BaseModel):
    server: str
    tool: str
    ok: bool
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/servers", response_model=list[McpServerOut])
async def api_mcp_servers(
    current_user: CurrentUser = Depends(verify_admin_auth),
) -> list[McpServerOut]:
    """Inventaire des serveurs MCP declares (§39).

    Lecture seule : ne demarre AUCUN sous-processus. Le regime
    "started" ci-dessous reflete le pool de sessions, pas le registre.
    """
    registry = get_registry()
    pool = get_pool()
    live = set(pool.active_keys())
    servers: list[McpServerOut] = []
    for cfg in registry.list():
        started = any(k.startswith(f"{cfg.name}:") for k in live)
        servers.append(
            McpServerOut(
                name=cfg.name,
                transport=cfg.transport,
                enabled=cfg.enabled,
                capabilities=list(cfg.capabilities),
                allowed_workflows=list(cfg.allowed_workflows),
                timeout_s=cfg.timeout_s,
                rate_limit=cfg.rate_limit,
                description=(
                    "Session ouverte" if started else "Session fermée (à la demande)"
                ),
            )
        )
    return servers


def _is_timeout(exc: BaseException) -> bool:
    """Vrai si `exc` signale un depasse de delai — et NON une panne.

    Deux formes coexistent, et les confondre enverrait un delai normal
    en 502 « serveur casse » (faux diagnostic, fausse alarme audit) :

    - `asyncio.TimeoutError` (alias de `TimeoutError` depuis 3.11) :
      notre garde-fou cote appelant — `asyncio.wait_for` dans
      `McpConnection.call_tool`, avec la marge de 10 s — ou celui du
      serveur MCP lui-meme.
    - `McpError(code=408)` : ce que leve REELLEMENT la SDK `mcp` quand
      `read_timeout_seconds` est depasse. `mcp/shared/session.py`
      enveloppe l'attente dans `anyio.fail_after(timeout)` puis leve
      `McpError(ErrorData(code=httpx.codes.REQUEST_TIMEOUT, ...))`, donc
      408 — le code de `httpx.codes.REQUEST_TIMEOUT`.

    408 doit donc finir en 504 (delai), pas en 502 (transport casse).
    """
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(exc, McpError):
        return getattr(exc.error, "code", None) == 408
    return False


@router.get("/servers/{name}/tools", response_model=McpToolsOut)
async def api_mcp_tools(
    name: str,
    current_user: CurrentUser = Depends(verify_admin_auth),
) -> McpToolsOut:
    """Tools exposes par un serveur, avec leur JSON Schema d'entree.

    Demarre le sous-processus si necessaire (~5 s au premier appel,
    puis reutilise la session du pool). L'identite transmise au
    serveur est celle de l'admin connecte, jamais une valeur fournie
    par le client.
    """
    cfg = _resolve_server(name)
    user_id = current_user.user_id
    started = time.monotonic()
    try:
        session = await get_pool().acquire(cfg, user_id)
        result = await session.list_tools()
    except Exception as exc:
        if _is_timeout(exc):
            raise HTTPException(504, f"Serveur MCP '{name}' : delai depasse au demarrage")
        logger.warning("MCP inspect: list_tools echoue sur '%s'", name, exc_info=True)
        raise HTTPException(502, f"Serveur MCP '{name}' injoignable : {exc}")

    tools = [
        McpToolOut(
            name=getattr(t, "name", "") or "",
            description=getattr(t, "description", "") or "",
            input_schema=dict(getattr(t, "inputSchema", None) or {}),
            output_schema=(
                dict(getattr(t, "outputSchema", None) or {}) or None
                if getattr(t, "outputSchema", None)
                else None
            ),
        )
        for t in getattr(result, "tools", [])
    ]
    log_event(
        "MCP_INSPECTOR_LIST_TOOLS",
        user_id=user_id,
        tool_name=name,
        message=f"{len(tools)} tools (serveur={name})",
    )
    return McpToolsOut(
        server=name,
        tools=tools,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


@router.post("/servers/{name}/tools/{tool}/invoke", response_model=McpInvokeOut)
async def api_mcp_invoke(
    name: str,
    tool: str,
    payload: McpInvokeIn,
    current_user: CurrentUser = Depends(verify_admin_auth),
) -> McpInvokeOut:
    """Execute un tool MCP et renvoie son resultat brut.

    Le timeout vient du registre (`cfg.timeout_s`). Le rate-limit aussi.
    Les erreurs du tool sont RENVOYEES dans la reponse (`ok=False`)
    plutot que levees : une erreur metier (fichier trop gros, chemin
    refuse) est une information utile pour l'inspector, pas une panne
    HTTP. Seules les pannes de transport remontent en 5xx.
    """
    cfg = _resolve_server(name)
    user_id = current_user.user_id
    _check_rate_limit(cfg, user_id)

    started = time.monotonic()
    try:
        session = await get_pool().acquire(cfg, user_id)
    except Exception as exc:
        if _is_timeout(exc):
            raise HTTPException(
                504,
                f"Serveur MCP '{name}' : delai depasse ({cfg.timeout_s}s)",
            )
        logger.warning("MCP inspect: invoke, serveur %s injoignable", name, exc_info=True)
        raise HTTPException(502, f"Serveur MCP '{name}' injoignable : {exc}")

    # On verifie l'existence du tool AVANT de l'appeler. Sans cela, un
    # nom errone part au serveur, qui repond une erreur JSONRPC ; notre
    # `except Exception` la transformerait en 502 « panne », alors que
    # c'est une faute d'appel cote client. 404 est l'info juste.
    # `_serialize_content` n'est PAS reutilise ici : on ne veut que les
    # noms. Cout ~0 (la session est deja ouverte et list_tools est
    # l'operation la moins chere du protocole).
    try:
        available = await session.list_tools()
    except Exception as exc:
        if _is_timeout(exc):
            raise HTTPException(504, f"Serveur MCP '{name}' : delai depasse")
        logger.warning("MCP inspect: list_tools echoue (%s)", name, exc_info=True)
        raise HTTPException(502, f"Serveur MCP '{name}' injoignable : {exc}")

    known = sorted(getattr(t, "name", "") or "" for t in getattr(available, "tools", []))
    if tool not in known:
        raise HTTPException(
            404,
            f"Tool '{tool}' inexistant sur '{name}'. Disponibles : {known}",
        )

    try:
        result = await session.call_tool(
            tool,
            arguments=payload.arguments,
            read_timeout_seconds=cfg.timeout_s,
        )
    except Exception as exc:
        if _is_timeout(exc):
            raise HTTPException(
                504,
                f"Tool '{tool}' ({name}) : timeout de {cfg.timeout_s}s depasse",
            )
        logger.warning("MCP inspect: invoke echoue (%s/%s)", name, tool, exc_info=True)
        log_event(
            "MCP_INSPECTOR_INVOKE_FAILED",
            level="ERROR",
            user_id=user_id,
            tool_name=f"{name}/{tool}",
            message=str(exc),
        )
        raise HTTPException(502, f"Invocation impossible : {exc}")

    is_error = bool(getattr(result, "isError", False))
    error = None
    if is_error:
        texts = [
            b.get("text", "")
            for b in _serialize_content(getattr(result, "content", []))
        ]
        error = "\n".join(t for t in texts if t) or "Le tool a signale une erreur."

    duration_ms = int((time.monotonic() - started) * 1000)
    # Toute invocation admin est tracee : un tool d'ecriture touche des
    # donnees reelles, l'inspector doit laisser une trace consultable.
    log_event(
        "MCP_INSPECTOR_INVOKE_FAILED" if is_error else "MCP_INSPECTOR_INVOKE",
        level="ERROR" if is_error else "INFO",
        user_id=user_id,
        tool_name=f"{name}/{tool}",
        message=f"{tool} sur {name} en {duration_ms}ms"
        + (" (erreur)" if is_error else ""),
        extra={"duration_ms": duration_ms, "server": name},
    )
    return McpInvokeOut(
        server=name,
        tool=tool,
        ok=not is_error,
        content=_serialize_content(getattr(result, "content", [])),
        structured_content=getattr(result, "structuredContent", None),
        error=error,
        duration_ms=duration_ms,
    )