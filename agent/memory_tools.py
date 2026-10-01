"""Outils mémoire de l'agent vocal — accès HTTP à l'API Render.

Découplés de l'agent principal pour faciliter les tests et la maintenance.

## Pourquoi HTTP et pas un import

L'agent est déployé sur LiveKit Cloud depuis le dossier `agent/`, dans un
contexte de build **mono-dossier** : `app.services.memory.memory` ( LangGraph
store Postgres, cache Redis, logging événementiel ) n'y est pas importable.
L'API Render reste donc propriétaire de la mémoire — voir ADR-026.

Avantage : **aucune duplication** de la logique mémoire, et plus de cache à
propager entre deux processus ( lectures et écritures passent par la même API ).

## Contrat volontairement identique

Les 4 outils portent les **mêmes noms, mêmes signatures et mêmes types de
retour** que ceux du worker Render retiré ( historique git :
`backend/app/infrastructure/livekit/memory_tools.py` ). Le vocabulaire d'outils
vu par le LLM ne change donc pas d'une architecture à l'autre, et les réponses
sont unwrappées côté agent pour retrouver la forme exacte renvoyée par
`memory.py` ( une liste de faits, pas un enveloppe ).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from livekit.agents import RunContext, function_tool

logger = logging.getLogger("agent-tutor.memory-tools")

#: Timeout court : un outil mémoire lent fait perdre la fluidité de la session
#: vocale. Mieux vaut renvoyer vide que bloquer l'agent.
HTTP_TIMEOUT_S = 8.0

#: Catégories autorisées — même source unique que le prompt (`config.py`).
ALLOWED_CATEGORIES = frozenset(
    {"identity", "background", "personality", "preference", "interest"}
)

#: Vocabulaire d'outils ( conserved depuis le worker Render ).
MEMORY_TOOLS = [
    "get_user_profile",
    "get_user_memory",
    "search_user_memory",
    "save_user_memory",
]


def _api_url() -> str:
    return os.getenv("AGENT_API_URL", "").rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "X-Service-Secret": os.getenv("AGENT_SERVICE_SECRET", "").strip(),
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, params: dict | None = None) -> Any:
    """Appelle l'API mémoire. Lève en cas d'échec réseau ou HTTP."""
    base = _api_url()
    if not base:
        raise RuntimeError("AGENT_API_URL non configurée")

    url = f"{base}/api/agent-memory{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"

    data = None
    if method == "POST":
        data = json.dumps(params or {}).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _safe(call, fallback: Any, tool: str) -> Any:
    """Ne jamais laisser une panne mémoire tuer la session vocale.

    L'agent doit pouvoir continuer à enseigner sans mémoire : on journalise et
    on renvoie une structure vide, que le LLM interprets comme « rien connu ».
    """
    try:
        return call()
    except urllib.error.HTTPError as exc:
        logger.warning("Outil mémoire %s : HTTP %s", tool, exc.code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Outil mémoire %s : %s: %s", tool, type(exc).__name__, exc)
    return fallback


def fetch_memory_context(user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Charge profil + aperçu mémoire en UN appel — au démarrage de la session.

    Renvoie le couple `(profile, overview)` attendu par
    `config.build_system_instructions()`. En cas de panne ( API injoignable,
    secret absent, store indisponible ) renvoie `({}, {})` : l'agent démarre
    sans mémoire plutôt que de perdre la session.
    """
    payload = _safe(
        lambda: _request("GET", f"/{user_id}/overview"),
        {},
        "fetch_memory_context",
    )
    if not isinstance(payload, dict) or not payload:
        return {}, {}

    # `identity` porte name/description ; le reste de la charge utile est
    # exactement la forme attendue par build_system_instructions.
    identity = payload.get("identity")
    profile = identity if isinstance(identity, dict) else {}
    return profile, payload


@function_tool
async def get_user_profile(
    context: RunContext,
    user_id: str,
) -> dict[str, Any]:
    """Retourne le profil longue durée de l'étudiant."""
    payload = _safe(
        lambda: _request("GET", f"/{user_id}/profile"),
        {},
        "get_user_profile",
    )
    return payload if isinstance(payload, dict) else {}


@function_tool
async def get_user_memory(
    context: RunContext,
    user_id: str,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Retourne les faits mémorisés de l'étudiant.

    Args:
        user_id: ID de l'utilisateur
        category: Filtrer par catégorie (identity, background, personality, preference, interest).
                  Si None, retourne toutes les catégories.
    """
    payload = _safe(
        lambda: _request("GET", f"/{user_id}/facts", {"category": category}),
        {},
        "get_user_memory",
    )
    return payload.get("facts", []) if isinstance(payload, dict) else []


@function_tool
async def search_user_memory(
    context: RunContext,
    user_id: str,
    query: str,
) -> list[dict[str, Any]]:
    """Recherche les souvenirs pertinents pour une requête."""
    payload = _safe(
        lambda: _request("GET", f"/{user_id}/search", {"q": query}),
        {},
        "search_user_memory",
    )
    return payload.get("facts", []) if isinstance(payload, dict) else []


@function_tool
async def save_user_memory(
    context: RunContext,
    user_id: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Enregistre un fait durable explicitement déclaré par l'étudiant."""
    if category not in ALLOWED_CATEGORIES:
        return {
            "success": False,
            "error": f"Catégorie inconnue : {category}",
        }

    payload = _safe(
        lambda: _request(
            "POST",
            f"/{user_id}/facts",
            {"category": category, "content": content, "confidence": 1.0},
        ),
        {},
        "save_user_memory",
    )
    if not isinstance(payload, dict) or not payload.get("saved"):
        return {"success": False, "error": "Écriture refusée par l'API"}

    fact = payload.get("fact", {})
    return {"success": True, **fact}