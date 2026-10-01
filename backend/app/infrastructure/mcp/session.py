"""Sessions MCP persistantes (piscine) — inspection et debug d'outils.

Pourquoi ce module existe
-------------------------
`MultiServerMCPClient` (langchain-mcp-adapters 0.3.2) n'EXPOSE PLUS de
session persistante : `client.session()` est un `@asynccontextmanager`
qui ouvre un sous-processus, yield la session, puis le ferme en sortant
(« starting a new session on each tool call »). Il n'y a plus d'
`exit_stack` sur l'instance — vérifié par introspection :
`instance attrs == ['callbacks', 'connections', 'handle_tool_errors',
'tool_interceptors', 'tool_name_prefix']`.

Or un serveur stdio met ~5 s à démarrer (cold imports FastMCP,
SQLAlchemy, Pydantic) : recréer un sous-processus par clic dans un
inspecteur rend l'outil inutilisable. Ce module reconstruit la
persistance sur le SDK `mcp` BRUT — le même que celui qu'écrivent nos
serveurs (FastMCP).

PROBLÈME CENTRAL : LES SCOPES ANYIO SONT LIÉS À LA TÂCHE
-------------------------------------------------------
`stdio_client` ouvre un `anyio.create_task_group()`. Un cancel scope
anyio ne peut être FERMÉ que par la tâche qui l'a OUVERT :

    RuntimeError: Attempted to exit cancel scope in a different task
    than it was entered in

Or dans une API web, chaque requête HTTP est une TÂCHE distincte. Si on
persiste un `AsyncExitStack` dans un dict (design naïf), on obtient :

  - création  : tâche de la requête qui clique la 1re fois
  - usage     : tâches des requêtes suivantes
  - fermeture : tâche de l'éviction TTL, ou tâche du lifespan shutdown

Aucune des fermetures ne se fait donc dans la tâche d'ouverture. Le
teardown échoue, la génératrice `stdio_client` reste NON finalisée
(« async generator ignored GeneratorExit » au passage du GC) et rien ne
garantit plus la mort du sous-processus. Vérifié empiriquement, pas
déduit.

SOLUTION : UNE TÂCHE PROPRIÉTAIRE PAR SESSION (`McpConnection`)
--------------------------------------------------------------
La tâche propriétaire ouvre le `stdio_client` ET la `ClientSession`,
exécute TOUS les appels, et ferme le stack — dans SA tâche. Les autres
tâches ne touchent jamais aux scopes : elles déposent une demande dans
une `asyncio.Queue` et attendent un `Future`. `McpConnection` expose
`list_tools()` / `call_tool(...)`, miroir exact de `ClientSession`, donc
les appelants (API admin) ne voient aucune différence.

Sécurité (§39/§40/§41) — rien n'est relâché
-------------------------------------------
- On ne se connecte qu'à des serveurs déjà autorisés par le registre
  (`McpRegistry.get`, qui filtre sur `enabled`). Le caller ne fournit
  qu'un NOM : aucune connexion à un serveur arbitraire.
- L'identité vient de l'appelant (`user_id` interne de `CurrentUser`),
  jamais d'un paramètre de requête libre. Elle est propagée par env
  subprocess exactement comme le fait `toolset.py`, donc les garde-fous
  des serveurs (`_validate`, `_guard_size`, tables par `user_id`)
  s'appliquent INCHANGÉS.
- `os.environ` n'est PAS transmis au sous-processus : `stdio_client`
  fusionne `get_default_environment()` (12 variables Windows : PATH,
  TEMP...) avec `server.env`. Les secrets du process parent ne fuient
  donc pas. `DATABASE_URL` n'en a pas besoin : le serveur recharge
  `backend/.env` lui-même via `app.config`, et `BACKEND_DIR` dérive de
  `__file__` (pas du CWD) -> insensible au répertoire de lancement.
- `PYTHONPATH` est fourni par `registry._default_servers()` (dans
  `cfg.env`), sans quoi `import app` échoue dans le sous-processus.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

# TTL d'inactivite avant eviction d'une session : assez long pour
# qu'un humain explore les tools sans rouvrir un sous-processus a chaque
# clic, assez court pour ne pas laisser vivre des processus orphelins
# d'une session de debug oubliee.
SESSION_TTL_SECONDS = 900.0
# Plafond dur : meme tres actif, on recycle le sous-processus. Un
# serveur MCP de debug n'a aucune raison de vivre plusieurs heures, et
# cela borne la casse si un serveur se retrouve dans un etat degrade
# (sous-processus bloque, pipe sature).
SESSION_MAX_AGE_SECONDS = 3600.0

# Marge ajoutee au timeout du registre pour l'attente COTE APPELANT.
# Le `read_timeout_seconds` de la SDK borne l'appel MCP lui-meme ; cette
# marge couvre en plus le cas ou la tache proprietaire serait bloquee
# (sous-processus qui ignore le timeout). Sans elle, la requete HTTP
# resterait suspendue indefiniment.
_CALLER_TIMEOUT_MARGIN_S = 10.0

# Sentinelle d'arret deposee dans la file de la tache proprietaire.
_SHUTDOWN = object()


def env_for_server(cfg: Any, user_id: str) -> dict[str, str]:
    """Env du sous-processus stdio pour une config donnee.

    Meme contrat que `toolset.py` : on part de `cfg.env` (allowlist,
    jamais de secret — voir `McpServerConfig.env`) puis on impose
    l'identite. On NE copie PAS `os.environ`.

    `MCP_FS_USER_ID` / `MCP_CAL_USER_ID` ne sont pas seulement une
    convention : les serveurs les exigent au demarrage (sans elles, le
    serveur sort et la connexion se ferme — `McpError: Connection
    closed` a l'`initialize()`).
    """
    env: dict[str, str] = {str(k): str(v) for k, v in (cfg.env or {}).items()}
    if user_id:
        env["MCP_FS_USER_ID"] = user_id
        env["MCP_CAL_USER_ID"] = user_id
    return env


class McpConnection:
    """Une session MCP possédée par une tâche dédiée.

    Voir le docstring du module pour le POURQUOI (cancel scopes anyio
    liés à la tâche). Le contrat public imite `ClientSession` :

        conn = await pool.acquire(cfg, user_id)
        res = await conn.list_tools()
        res = await conn.call_tool("read_file", arguments={...},
                                   read_timeout_seconds=20.0)
    """

    def __init__(self, name: str, user_id: str) -> None:
        self.name = name
        self.user_id = user_id
        now = time.monotonic()
        self.created_at = now
        self.last_used = now
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._closed = False

    # -- introspection --------------------------------------------------

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done() and not self._closed

    # -- API publique (miroir de ClientSession) -------------------------

    async def list_tools(self) -> Any:
        return await self._submit("list_tools", None)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: float | None = None,
    ) -> Any:
        """Execute un tool via la tache proprietaire.

        `read_timeout_seconds` est transmis a la SDK (borne l'appel MCP
        cote serveur). On y ajoute, cote appelant, une marge pour ne pas
        rester suspendu si la tache proprietaire est elle-meme bloquee.
        """
        args = (name, arguments, read_timeout_seconds)
        if read_timeout_seconds:
            budget = float(read_timeout_seconds) + _CALLER_TIMEOUT_MARGIN_S
            return await asyncio.wait_for(self._submit("call_tool", args), budget)
        return await self._submit("call_tool", args)

    async def _submit(self, op: str, args: Any) -> Any:
        if not self.alive:
            raise ConnectionError(f"Session MCP '{self.name}' fermee")
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put((op, args, fut))
        return await fut

    # -- cycle de vie ---------------------------------------------------

    async def start(self, cfg: Any) -> None:
        """Demarre la tache proprietaire et attend l'`initialize()`.

        Laisse remonter l'echec (serveur qui ne demarre pas) : l'appelant
        le transforme en erreur explicite cote API.
        """
        self._ready = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run(cfg), name=f"mcp:{self.name}")
        await self._ready

    async def _run(self, cfg: Any) -> None:
        """Tache proprietaire : ouvre, sert, ferme. Tout dans CETTE tache."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=cfg.command,
            args=list(cfg.args or []),
            env=env_for_server(cfg, self.user_id),
        )
        stack = contextlib.AsyncExitStack()
        session: Any = None
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException as exc:
            # Teardown DANS la tache d'ouverture : legal.
            await self._aclose_stack(stack)
            self._fail_ready(exc)
            return
        self._resolve_ready()
        logger.info("MCP session ouverte: %s (user=%s)", self.name, self.user_id or "-")

        try:
            while True:
                op, args, fut = await self._queue.get()
                if op is _SHUTDOWN:
                    self._set_result(fut, None)
                    break
                await self._handle(session, op, args, fut)
        finally:
            self._closed = True
            self._drain_pending()
            # Fermeture dans la tache proprietaire -> le cancel scope
            # anyio est bien ferme par celle qui l'a ouvert.
            await self._aclose_stack(stack)
            logger.debug("MCP session fermee: %s", self.name)

    async def _handle(self, session: Any, op: str, args: Any, fut: asyncio.Future) -> None:
        try:
            if op == "list_tools":
                result = await session.list_tools()
            elif op == "call_tool":
                tool, arguments, read_timeout = args
                # La SDK attend un `datetime.timedelta`, PAS un float :
                # `mcp/shared/session.py` fait
                # `request_read_timeout_seconds.total_seconds()`, donc un
                # float leve `AttributeError: 'float' object has no
                # attribute 'total_seconds'`. Notre unite d'entree est le
                # float `cfg.timeout_s` du registre ; on convertit ici, a
                # la frontiere de la SDK, pour que les appelants n'aient
                # pas a connaitre le type attendu en interne.
                sdk_timeout = (
                    timedelta(seconds=float(read_timeout)) if read_timeout else None
                )
                result = await session.call_tool(
                    tool,
                    arguments=arguments,
                    read_timeout_seconds=sdk_timeout,
                )
            else:
                raise ValueError(f"Operation inconnue : {op}")
        except BaseException as exc:  # noqa: BLE001 — renvoye a l'appelant
            self._set_exception(fut, exc)
        else:
            self._set_result(fut, result)

    async def close(self) -> None:
        """Demande l'arret a la tache proprietaire et l'attend.

        Ne leve jamais : c'est une operation de nettoyage (eviction TTL
        ou shutdown). L'arret est demande via la file, donc c'est bien
        la tache proprietaire qui depile et ferme le stack.
        """
        task = self._task
        if task is None or task.done():
            self._closed = True
            return
        self._closed = True
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        try:
            await self._queue.put((_SHUTDOWN, None, fut))
            await asyncio.wait_for(asyncio.shield(fut), timeout=15.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # La tache proprietaire ne repond pas : on l'annule en
            # dernier recours. Son `finally` fermera le stack.
            task.cancel()
        except Exception:
            logger.warning("MCP: arret de la session %s en erreur", self.name, exc_info=True)
        try:
            await task
        except BaseException:
            # Annulation / erreur de teardown : deja journalise.
            pass

    # -- helpers --------------------------------------------------------

    def _resolve_ready(self) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.set_result(None)

    def _fail_ready(self, exc: BaseException) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.set_exception(exc)

    def _drain_pending(self) -> None:
        """Reveille les appelants en attente : la session est finie."""
        while True:
            try:
                _op, _args, fut = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._set_exception(fut, ConnectionError(f"Session MCP '{self.name}' fermee"))

    @staticmethod
    def _set_result(fut: asyncio.Future, value: Any) -> None:
        if not fut.done():
            fut.set_result(value)

    @staticmethod
    def _set_exception(fut: asyncio.Future, exc: BaseException) -> None:
        """Pose une exception sans laisser de 'never retrieved' si annule."""
        if not fut.done():
            fut.set_exception(exc)
        else:
            # Future annule par `wait_for` cote appelant : l'erreur
            # n'interesse plus personne, on l'abandonne proprement.
            logger.debug("MCP: resultat abandonne (appelant parti) : %r", exc)

    @staticmethod
    async def _aclose_stack(stack: contextlib.AsyncExitStack) -> None:
        try:
            await stack.aclose()
        except asyncio.CancelledError:
            # Artefact de cancel scope anyio pendant le teardown : on
            # est deja en train de tout demonter, rien a propager.
            return
        except BaseException:
            logger.warning("MCP: teardown de session en erreur", exc_info=True)


class McpSessionPool:
    """Piscine de sessions MCP persistantes, keyee (server, user).

    Safe en concurrence : un lock global sur la table + un re-check sous
    ce lock avant creation, pour que deux clics simultanes sur le meme
    tool ne demarrent pas deux sous-processus.

    Les sous-processus ne sont jamais laisses a l'abandon : eviction
    TTL a chaque acces, puis `close_all()` au shutdown. Chaque `close()`
    est effectue PAR la tache proprietaire de la session.
    """

    def __init__(
        self,
        ttl_seconds: float = SESSION_TTL_SECONDS,
        max_age_seconds: float = SESSION_MAX_AGE_SECONDS,
    ) -> None:
        self._conns: dict[tuple[str, str], McpConnection] = {}
        self._ttl = ttl_seconds
        self._max_age = max_age_seconds
        self._guard = asyncio.Lock()

    # -- introspection (health / tests) ---------------------------------

    def active_count(self) -> int:
        return len(self._conns)

    def active_keys(self) -> list[str]:
        return [f"{name}:{user or '-'}" for name, user in self._conns]

    # -- coeur ----------------------------------------------------------

    async def acquire(self, cfg: Any, user_id: str = "") -> McpConnection:
        """Retourne une connexion INITIALISEE pour `cfg`, en la reutilisant.

        Laisse remonter l'echec si le serveur ne demarre pas : l'appelant
        le transforme en erreur explicite cote API.
        """
        key = (cfg.name, user_id or "")
        now = time.monotonic()
        await self._evict_expired(now)

        conn = self._conns.get(key)
        if conn is not None and conn.alive:
            conn.last_used = now
            return conn

        async with self._guard:
            # Re-check sous lock : une autre tache a pu creer l'entree
            # entre notre lecture et l'acquisition du lock.
            conn = self._conns.get(key)
            if conn is not None and conn.alive:
                conn.last_used = now
                return conn
            conn = McpConnection(cfg.name, user_id or "")
            # Le demarrage (~5 s) se fait sous le lock. Pour un outil
            # d'admin mono-utilisateur, la simplicite prime : deux clics
            # simultanes ne creent jamais deux sous-processus.
            await conn.start(cfg)
            conn.last_used = time.monotonic()
            self._conns[key] = conn
            return conn

    async def drop(self, server_name: str, user_id: str = "") -> None:
        """Ferme la session d'un couple (server, user), si elle existe."""
        async with self._guard:
            conn = self._conns.pop((server_name, user_id or ""), None)
        if conn is not None:
            await conn.close()

    async def close_all(self) -> None:
        """Ferme TOUTES les sessions. A appeler au shutdown du serveur."""
        async with self._guard:
            conns = list(self._conns.values())
            self._conns.clear()
        for conn in conns:
            await conn.close()

    # -- eviction --------------------------------------------------------

    async def _evict_expired(self, now: float) -> None:
        """Ferme les sessions inactives depuis plus de le TTL (ou trop
        vieilles). ASYNCHRONE a dessein : la fermeture touche des
        sous-processus, on ne peut pas la faire depuis un helper sync.
        """
        async with self._guard:
            stale = [
                conn
                for conn in self._conns.values()
                if (now - conn.last_used) > self._ttl
                or (now - conn.created_at) > self._max_age
            ]
            for conn in stale:
                self._conns.pop((conn.name, conn.user_id), None)
        # Fermeture hors du lock : `close()` attend la fin de la tache
        # proprietaire et ne doit pas serialiser les autres acquisitions.
        for conn in stale:
            await conn.close()


# Pool applicatif — un par process, comme `get_registry()`.
_pool: McpSessionPool | None = None


def get_pool() -> McpSessionPool:
    """Piscine paresseuse (creee au premier appel reellement utile)."""
    global _pool
    if _pool is None:
        _pool = McpSessionPool()
    return _pool


async def close_all_sessions() -> None:
    """Ferme toutes les sessions MCP ouvertes. Ne leve JAMAIS.

    A appeler depuis le lifespan shutdown de `app/main.py`, a cote de
    `shutdown_langfuse()`.
    """
    pool = _pool
    if pool is None:
        return
    try:
        await pool.close_all()
        logger.info("MCP : toutes les sessions fermees")
    except Exception:
        logger.warning("MCP : fermeture des sessions echouee (ignore)", exc_info=True)


__all__ = [
    "McpConnection",
    "McpSessionPool",
    "SESSION_TTL_SECONDS",
    "SESSION_MAX_AGE_SECONDS",
    "env_for_server",
    "get_pool",
    "close_all_sessions",
]
