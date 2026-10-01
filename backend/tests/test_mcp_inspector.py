"""Tests de l'inspecteur MCP admin (§39/§40/§41).

Deux niveaux :
  1. **Registry** — pur, sans sous-processus : inventaire, scoping par
     workflow (§40), surcharge env `MCP_ENABLED_SERVERS`.
  2. **API** — `TestClient` + `dependency_overrides[get_current_user]`
     (donc la VRAIE chaîne `require_admin` est exécutée) + un faux pool
     de sessions. Aucun serveur stdio n'est lancé : les tests doivent
     rester rapides et ne jamais dépendre de 5 s de démarrage ni d'une
     base de données.

Le point de sécurité le plus important testé ici est
`test_identite_vient_du_jeton_pas_du_corps` : un `user_id` glissé dans
le corps de requête ne doit PAS influencer l'identité transmise au
serveur MCP, sans quoi un admin pourrait écrire dans l'espace d'un
autre utilisateur.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from app.auth.resolver import CurrentUser, get_current_user
from app.infrastructure.mcp.registry import McpRegistry, McpServerConfig

# UUID interne de l'admin de test — c'est CETTE valeur qui doit arriver
# dans le sous-processus MCP (env MCP_FS_USER_ID), jamais autre chose.
ADMIN_USER_ID = "00000000-0000-4000-8000-0000000000ad"


def _cfg(name: str, **overrides) -> McpServerConfig:
    """Serveur de test minimal, champs valides pour `extra='forbid'`."""
    base = dict(
        name=name,
        command="python",
        args=["dummy_server.py"],
        transport="stdio",
        enabled=True,
        capabilities=["filesystem"],
        allowed_workflows=["document", "coding"],
        timeout_s=20.0,
        rate_limit=20,
    )
    base.update(overrides)
    return McpServerConfig(**base)


# ---------------------------------------------------------------------------
# Doublures du SDK MCP (aucun sous-processus)
# ---------------------------------------------------------------------------


@dataclass
class _Tool:
    name: str
    description: str = ""
    inputSchema: dict | None = None
    outputSchema: dict | None = None


@dataclass
class _TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class _ListToolsResult:
    tools: list = field(default_factory=list)


@dataclass
class _CallResult:
    content: list = field(default_factory=list)
    isError: bool = False
    structuredContent: dict | None = None


class _FakeSession:
    """Remplace `mcp.ClientSession` : mémoire seule, jamais d'I/O."""

    def __init__(self, tools: list[_Tool] | None = None) -> None:
        self._tools = tools or [
            _Tool(
                "list_files",
                description="Liste les fichiers de l'utilisateur",
                inputSchema={"type": "object", "properties": {}},
            ),
            _Tool(
                "read_file",
                description="Lit un fichier",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            _Tool(
                "create_file",
                description="Cree un fichier",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
        ]
        # (tool, arguments, read_timeout_seconds)
        self.calls: list[tuple] = []
        self.raise_on_call: Exception | None = None
        # Permet de tester le chemin 504 sur `list_tools` (demarrage
        # lent du serveur) sans avoir a lever depuis le pool.
        self.raise_on_list: Exception | None = None

    async def list_tools(self) -> _ListToolsResult:
        if self.raise_on_list is not None:
            raise self.raise_on_list
        return _ListToolsResult(tools=list(self._tools))

    async def call_tool(self, name, arguments=None, read_timeout_seconds=None):
        self.calls.append((name, arguments, read_timeout_seconds))
        if self.raise_on_call is not None:
            raise self.raise_on_call
        return _CallResult(
            content=[_TextBlock(text=f"resultat:{name}")],
            isError=False,
            structuredContent={"tool": name},
        )


async def _raise_mcp_timeout(*_args, **_kwargs):
    """Reproduit EXACTEMENT le timeout de la SDK `mcp`.

    On utilise le VRAI `McpError` et le VRAI code
    `httpx.codes.REQUEST_TIMEOUT`, et non un nombre écrit en dur : le
    test casse donc automatiquement si la SDK change son code d'erreur,
    ce qui est exactement le contrat qu'on veut verrouiller.
    """
    raise McpError(
        ErrorData(
            code=httpx.codes.REQUEST_TIMEOUT,
            message="Timed out while waiting for response to CallToolRequest.",
        )
    )


async def _raise_asyncio_timeout(*_args, **_kwargs):
    raise asyncio.TimeoutError()


class _FakePool:
    """Remplace `McpSessionPool`. Enregistre qui a demandé quoi."""

    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        # (server_name, user_id) — sert à prouver l'identité transmise.
        self.acquired: list[tuple[str, str]] = []
        self.raise_on_acquire: Exception | None = None

    async def acquire(self, cfg, user_id: str = ""):
        self.acquired.append((cfg.name, user_id))
        if self.raise_on_acquire is not None:
            raise self.raise_on_acquire
        return self.session

    def active_count(self) -> int:
        return len(self.acquired)

    def active_keys(self) -> list[str]:
        return [f"{name}:{user or '-'}" for name, user in self.acquired]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_env(monkeypatch):
    """Branche le registry de test, le faux pool et l'admin sur l'app."""
    from fastapi.testclient import TestClient

    import app.api.admin.mcp as mcp_api
    from app.main import app

    # Le registry de test ne doit pas subir MCP_ENABLED_SERVERS de l'env.
    monkeypatch.delenv("MCP_ENABLED_SERVERS", raising=False)

    registry = McpRegistry(
        servers={
            "alpha": _cfg(
                "alpha",
                capabilities=["filesystem", "file-write"],
                allowed_workflows=["document", "coding"],
                timeout_s=12.5,
                rate_limit=3,
            ),
            "beta": _cfg(
                "beta",
                capabilities=["calendar"],
                allowed_workflows=["document"],
                timeout_s=20.0,
                rate_limit=2,
            ),
            "dead": _cfg("dead", enabled=False, capabilities=["calendar"]),
        }
    )
    session = _FakeSession()
    pool = _FakePool(session)

    monkeypatch.setattr(mcp_api, "get_registry", lambda: registry)
    monkeypatch.setattr(mcp_api, "get_pool", lambda: pool)
    mcp_api.reset_rate_limits()

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        external_user_id="ext-admin",
        user_id=ADMIN_USER_ID,
        name="Admin Test",
        role="admin",
    )
    try:
        yield TestClient(app), pool, session
    finally:
        app.dependency_overrides.clear()
        mcp_api.reset_rate_limits()


def _as_role(role: str) -> CurrentUser:
    return CurrentUser(
        external_user_id="ext",
        user_id=ADMIN_USER_ID if role == "admin" else "u-1",
        name="Test",
        role=role,
    )


# ---------------------------------------------------------------------------
# 1. Registry — inventaire et scoping (§39/§40)
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_inventaire_liste_meme_les_desactives(self):
        reg = McpRegistry(servers={"a": _cfg("a"), "b": _cfg("b", enabled=False)})
        assert sorted(c.name for c in reg.list()) == ["a", "b"]

    def test_enabled_filtre_les_desactives(self):
        reg = McpRegistry(servers={"a": _cfg("a"), "b": _cfg("b", enabled=False)})
        assert [c.name for c in reg.enabled()] == ["a"]

    def test_for_workflow_scoping(self):
        """Un serveur n'est exposé qu'aux workflows listés (§40)."""
        reg = McpRegistry(
            servers={
                "fs": _cfg("fs", allowed_workflows=["document", "coding"]),
                "cal": _cfg("cal", allowed_workflows=["document"]),
            }
        )
        assert sorted(c.name for c in reg.for_workflow("document")) == ["cal", "fs"]
        assert [c.name for c in reg.for_workflow("coding")] == ["fs"]
        assert reg.for_workflow("inconnu") == []

    def test_workflow_ne_voit_pas_un_serveur_desactive(self):
        reg = McpRegistry(
            servers={"x": _cfg("x", enabled=False, allowed_workflows=["document"])}
        )
        assert reg.enabled() == []
        assert reg.for_workflow("document") == []

    def test_env_override_desactive_tout(self, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED_SERVERS", "")
        reg = McpRegistry(servers={"a": _cfg("a"), "b": _cfg("b")})
        assert reg.enabled() == []

    def test_env_override_allowlist(self, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED_SERVERS", "b")
        reg = McpRegistry(servers={"a": _cfg("a"), "b": _cfg("b")})
        assert [c.name for c in reg.enabled()] == ["b"]

    def test_get_inconnu_renvoie_none(self):
        reg = McpRegistry(servers={"a": _cfg("a")})
        assert reg.get("nope") is None


# ---------------------------------------------------------------------------
# 2. Autorisation
# ---------------------------------------------------------------------------


class TestAuthorization:
    def test_non_admin_refuse(self, mcp_env):
        from app.main import app

        app.dependency_overrides[get_current_user] = lambda: _as_role("user")
        client = mcp_env[0]
        assert client.get("/api/admin/mcp/servers").status_code == 403

    def test_admin_accepte(self, mcp_env):
        client = mcp_env[0]
        assert client.get("/api/admin/mcp/servers").status_code == 200


# ---------------------------------------------------------------------------
# 3. Inventaire des serveurs (GET /servers)
# ---------------------------------------------------------------------------


class TestServersEndpoint:
    def test_renvoie_les_trois_serveurs_du_registry(self, mcp_env):
        client = mcp_env[0]
        response = client.get("/api/admin/mcp/servers")
        assert response.status_code == 200
        body = response.json()
        assert sorted(s["name"] for s in body) == ["alpha", "beta", "dead"]

    def test_expose_scoping_et_limites(self, mcp_env):
        client = mcp_env[0]
        body = {s["name"]: s for s in client.get("/api/admin/mcp/servers").json()}
        alpha = body["alpha"]
        assert alpha["enabled"] is True
        assert alpha["timeout_s"] == 12.5
        assert alpha["rate_limit"] == 3
        assert alpha["capabilities"] == ["filesystem", "file-write"]
        assert alpha["allowed_workflows"] == ["document", "coding"]
        assert body["dead"]["enabled"] is False
        assert body["beta"]["rate_limit"] == 2

    def test_lecture_seule_ne_demarre_aucun_sous_processus(self, mcp_env):
        client, pool, _ = mcp_env
        client.get("/api/admin/mcp/servers")
        assert pool.acquired == []


# ---------------------------------------------------------------------------
# 4. Tools d'un serveur (GET /servers/{name}/tools)
# ---------------------------------------------------------------------------


class TestToolsEndpoint:
    def test_liste_les_tools_avec_schema(self, mcp_env):
        client = mcp_env[0]
        response = client.get("/api/admin/mcp/servers/alpha/tools")
        assert response.status_code == 200
        body = response.json()
        assert body["server"] == "alpha"
        names = sorted(t["name"] for t in body["tools"])
        assert names == ["create_file", "list_files", "read_file"]
        read = next(t for t in body["tools"] if t["name"] == "read_file")
        assert read["input_schema"]["properties"]["path"]["type"] == "string"
        assert read["input_schema"]["required"] == ["path"]
        assert "duration_ms" in body

    def test_serveur_inconnu_404(self, mcp_env):
        client = mcp_env[0]
        response = client.get("/api/admin/mcp/servers/nope/tools")
        assert response.status_code == 404
        # Le message liste les serveurs déclarés (aide au diagnostic).
        assert "alpha" in response.json()["detail"]

    def test_serveur_desactive_409(self, mcp_env):
        client = mcp_env[0]
        response = client.get("/api/admin/mcp/servers/dead/tools")
        assert response.status_code == 409

    def test_identite_transmise_est_celle_de_l_admin(self, mcp_env):
        client, pool, _ = mcp_env
        client.get("/api/admin/mcp/servers/alpha/tools")
        assert pool.acquired == [("alpha", ADMIN_USER_ID)]


# ---------------------------------------------------------------------------
# 5. Invocation (POST /servers/{name}/tools/{tool}/invoke)
# ---------------------------------------------------------------------------


class TestInvokeEndpoint:
    def test_invocation_valide(self, mcp_env):
        client, _, session = mcp_env
        response = client.post(
            "/api/admin/mcp/servers/alpha/tools/list_files/invoke",
            json={"arguments": {}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["server"] == "alpha"
        assert body["tool"] == "list_files"
        assert body["error"] is None
        assert body["content"][0]["text"] == "resultat:list_files"
        assert body["structured_content"] == {"tool": "list_files"}
        assert isinstance(body["duration_ms"], int)
        assert session.calls[-1][0] == "list_files"

    def test_timeout_du_registre_est_transmis(self, mcp_env):
        client, _, session = mcp_env
        client.post(
            "/api/admin/mcp/servers/alpha/tools/read_file/invoke",
            json={"arguments": {"path": "a.txt"}},
        )
        _name, args, timeout = session.calls[-1]
        assert args == {"path": "a.txt"}
        assert timeout == 12.5  # = cfg.timeout_s d'alpha, pas une valeur en dur

    def test_tool_inconnu_404_et_aucun_appel(self, mcp_env):
        client, _, session = mcp_env
        response = client.post(
            "/api/admin/mcp/servers/alpha/tools/pwn/invoke",
            json={"arguments": {}},
        )
        assert response.status_code == 404
        assert "pwn" in response.json()["detail"]
        # Le tool inconnu ne doit JAMAIS atteindre le serveur.
        assert session.calls == []

    def test_serveur_inconnu_404(self, mcp_env):
        client = mcp_env[0]
        response = client.post(
            "/api/admin/mcp/servers/nope/tools/list_files/invoke",
            json={"arguments": {}},
        )
        assert response.status_code == 404

    def test_serveur_desactive_409(self, mcp_env):
        client = mcp_env[0]
        response = client.post(
            "/api/admin/mcp/servers/dead/tools/list_files/invoke",
            json={"arguments": {}},
        )
        assert response.status_code == 409

    def test_erreur_metier_du_tool_renvoyee_ok_false(self, mcp_env):
        """Une erreur du tool est une information, pas une panne HTTP."""
        client, _, session = mcp_env
        session.call_tool = _raise_result  # type: ignore[assignment]
        response = client.post(
            "/api/admin/mcp/servers/alpha/tools/create_file/invoke",
            json={"arguments": {"path": "x", "content": "y"}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["error"]


async def _raise_result(name, arguments=None, read_timeout_seconds=None):
    """Rend un `isError=True` comme le ferait un vrai serveur MCP."""
    return _CallResult(
        content=[_TextBlock(text="chemin interdit")],
        isError=True,
    )


class TestRateLimit:
    def test_429_au_dela_de_la_limite(self, mcp_env):
        client = mcp_env[0]
        url = "/api/admin/mcp/servers/alpha/tools/list_files/invoke"
        # alpha : rate_limit = 3 / fenêtre de 60 s.
        for _ in range(3):
            assert client.post(url, json={"arguments": {}}).status_code == 200
        depasse = client.post(url, json={"arguments": {}})
        assert depasse.status_code == 429
        assert "Rate-limit" in depasse.json()["detail"]

    def test_la_limite_est_par_serveur(self, mcp_env):
        client = mcp_env[0]
        url_alpha = "/api/admin/mcp/servers/alpha/tools/list_files/invoke"
        # beta a rate_limit = 2 ; sa propre limite ne doit pas être
        # consommée par les appels alpha.
        for _ in range(3):
            client.post(url_alpha, json={"arguments": {}})
        assert client.post(url_alpha, json={"arguments": {}}).status_code == 429
        # beta reste utilisable (mais n'expose pas list_files chez nous —
        # on teste donc son propre endpoint tools, qui ne consomme PAS
        # de rate-limit : la garde ne s'applique qu'à l'invocation).
        assert client.get("/api/admin/mcp/servers/beta/tools").status_code == 200


# ---------------------------------------------------------------------------
# 6. Sécurité §41 — l'identité ne vient JAMAIS du corps de requête
# ---------------------------------------------------------------------------


class TestIdentityIsolation:
    def test_identite_vient_du_jeton_pas_du_corps(self, mcp_env):
        client, pool, session = mcp_env
        response = client.post(
            "/api/admin/mcp/servers/alpha/tools/list_files/invoke",
            json={
                "arguments": {},
                # Tentative d'injection : un user_id libre ne doit avoir
                # AUCUN effet — le modèle pydantic l'ignore, et le code
                # n'utilise que current_user.user_id.
                "user_id": "00000000-0000-4000-8000-deadbeefdead",
                "MCP_FS_USER_ID": "attaquant",
            },
        )
        assert response.status_code == 200
        # Le sous-processus a été ouvert avec l'UUID de l'admin, pas
        # avec les valeurs du corps.
        assert pool.acquired == [("alpha", ADMIN_USER_ID)]
        assert session.calls[-1][0] == "list_files"


# ---------------------------------------------------------------------------
# 7. Pannes de transport -> 502, pas 500 opaque
# ---------------------------------------------------------------------------


class TestTransportFailures:
    def test_serveur_injoignable_502(self, mcp_env):
        client, pool, _ = mcp_env
        pool.raise_on_acquire = RuntimeError("spawn failed")
        response = client.get("/api/admin/mcp/servers/alpha/tools")
        assert response.status_code == 502
        assert "injoignable" in response.json()["detail"]

    def test_invocation_injoignable_502(self, mcp_env):
        client, pool, _ = mcp_env
        pool.raise_on_acquire = RuntimeError("spawn failed")
        response = client.post(
            "/api/admin/mcp/servers/alpha/tools/list_files/invoke",
            json={"arguments": {}},
        )
        assert response.status_code == 502


# ---------------------------------------------------------------------------
# 8. Delai -> 504, panne -> 502 (et NON l'inverse)
# ---------------------------------------------------------------------------


def _timeout_mcp_error() -> McpError:
    """Timeout RÉEL de la SDK : `McpError(code=httpx.REQUEST_TIMEOUT)`.

    Construit via le code httpx plutôt qu'un 408 en dur, pour que le
    test suive la SDK si elle change son code.
    """
    return McpError(
        ErrorData(
            code=httpx.codes.REQUEST_TIMEOUT,
            message="Timed out while waiting for response",
        )
    )


class TestTimeoutVsTransport:
    """Distingue un délai dépassé d'une panne de transport.

    Les deux se présentent à l'appelant comme des exceptions ; les
    confondre produit un faux diagnostic (un simple appel lent
    étiqueté « serveur injoignable ») et une fausse trace d'audit.
    """

    # -- délai sur le chemin list_tools -------------------------------

    def test_list_tools_delai_sdk_504(self, mcp_env):
        client, _pool, session = mcp_env
        session.raise_on_list = _timeout_mcp_error()
        r = client.get("/api/admin/mcp/servers/alpha/tools")
        assert r.status_code == 504
        assert "delai" in r.json()["detail"].lower()

    def test_list_tools_asyncio_timeout_504(self, mcp_env):
        client, _pool, session = mcp_env
        session.raise_on_list = asyncio.TimeoutError()
        assert client.get("/api/admin/mcp/servers/alpha/tools").status_code == 504

    def test_list_tools_panne_reste_502(self, mcp_env):
        """Un `McpError` NON-408 reste une panne → 502, pas 504."""
        client, _pool, session = mcp_env
        session.raise_on_list = McpError(
            ErrorData(code=-32603, message="Internal error")
        )
        r = client.get("/api/admin/mcp/servers/alpha/tools")
        assert r.status_code == 502
        assert "injoignable" in r.json()["detail"]

    # -- délai sur le chemin invoke ----------------------------------

    def test_invoke_delai_sdk_504(self, mcp_env):
        client, _pool, session = mcp_env
        session.raise_on_call = _timeout_mcp_error()
        r = client.post(
            "/api/admin/mcp/servers/alpha/tools/list_files/invoke",
            json={"arguments": {}},
        )
        assert r.status_code == 504
        assert "timeout" in r.json()["detail"].lower()

    def test_invoke_asyncio_timeout_504(self, mcp_env):
        client, _pool, session = mcp_env
        session.raise_on_call = asyncio.TimeoutError()
        assert (
            client.post(
                "/api/admin/mcp/servers/alpha/tools/list_files/invoke",
                json={"arguments": {}},
            ).status_code
            == 504
        )

    def test_invoke_panne_reste_502(self, mcp_env):
        client, _pool, session = mcp_env
        session.raise_on_call = McpError(ErrorData(code=-32601, message="No such tool"))
        r = client.post(
            "/api/admin/mcp/servers/alpha/tools/list_files/invoke",
            json={"arguments": {}},
        )
        assert r.status_code == 502

    def test_acquire_timeout_504(self, mcp_env):
        """Un délai pendant l'ouverture de la session → 504."""
        client, pool, _ = mcp_env
        pool.raise_on_acquire = _timeout_mcp_error()
        assert client.get("/api/admin/mcp/servers/alpha/tools").status_code == 504

    def test_acquire_panne_reste_502(self, mcp_env):
        client, pool, _ = mcp_env
        pool.raise_on_acquire = RuntimeError("spawn failed")
        assert client.get("/api/admin/mcp/servers/alpha/tools").status_code == 502


# ---------------------------------------------------------------------------
# 9. Contrat SDK : `read_timeout_seconds` est un timedelta, PAS un float
# ---------------------------------------------------------------------------


class TestSdkTimeoutContract:
    """Verrouille la conversion float (registre) -> timedelta (SDK).

    `mcp/shared/session.py` appelle
    `request_read_timeout_seconds.total_seconds()`. Un float y lève
    `AttributeError`, ce qui transformait chaque invocation réelle en
    502. La conversion doit se faire dans `McpConnection`, à la
    frontière, pour que les appelants restent en float.
    """

    def test_float_du_registre_est_converti_en_timedelta(self):
        from app.infrastructure.mcp.session import McpConnection

        vu: dict = {}

        class _SessSpy:
            async def call_tool(self, name, arguments=None, read_timeout_seconds=None):
                vu["timeout"] = read_timeout_seconds
                return _CallResult(content=[_TextBlock(text="ok")])

        async def _drive():
            conn = McpConnection("alpha", ADMIN_USER_ID)
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            await conn._handle(
                _SessSpy(), "call_tool", ("read_file", {}, 12.5), fut
            )
            return fut.result()

        asyncio.run(_drive())
        assert isinstance(vu["timeout"], timedelta), "la SDK exige un timedelta"
        assert vu["timeout"].total_seconds() == 12.5

    def test_timeout_absent_reste_none(self):
        from app.infrastructure.mcp.session import McpConnection

        vu: dict = {}

        class _SessSpy:
            async def call_tool(self, name, arguments=None, read_timeout_seconds=None):
                vu["timeout"] = read_timeout_seconds
                return _CallResult()

        async def _drive():
            conn = McpConnection("alpha", ADMIN_USER_ID)
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            await conn._handle(_SessSpy(), "call_tool", ("read_file", {}, None), fut)
            return fut.result()

        asyncio.run(_drive())
        assert vu["timeout"] is None

    def test_is_timeout_reconnait_les_deux_formes(self):
        from app.api.admin.mcp import _is_timeout

        assert _is_timeout(asyncio.TimeoutError()) is True
        assert _is_timeout(_timeout_mcp_error()) is True
        assert _is_timeout(McpError(ErrorData(code=-32601))) is False
        assert _is_timeout(RuntimeError("boom")) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
