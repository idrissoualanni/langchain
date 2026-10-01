"""
API mémoire interne — service-à-service avec l'agent vocal LiveKit Cloud.

L'agent vocal est déployé sur LiveKit Cloud ( projet `live`, agent `tutor` ),
dans un **contexte de build mono-dossier** : il ne peut pas importer
`app.services.memory.memory` ( LangGraph store Postgres, cache, logging ).
L'API reste donc propriétaire de la mémoire et l'agent l'interroge en HTTP.

Conséquence d'architecture ( ADR-026 ) : lectures et écritures passent par le
**même** processus API, donc il n'y a plus de cache à propager entre deux
services — le défaut ADR-006bis a disparu par construction.

## Authentification

Pas de JWT utilisateur : l'agent n'a pas de session. Il s'authentifie avec un
secret partagé porté par l'en-tête `X-Service-Secret`, comparé en temps
constant à la variable d'environnement `AGENT_SERVICE_SECRET`.

- secret **non configuré** → 503 ( jamais d'endpoint ouvert par défaut )
- secret absent / faux    → 401

L'`user_id` présent dans le chemin n'est **pas** validé ici : il a été fourni
par l'API elle-même au dispatch ( metadata de job ), jamais par le client.
`GET /api/learning/{user_id}/profile` reste la route de lecture publique pour
le front — ce module ne fait que l'ouvrir au service agent.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.memory.memory import (
    list_facts,
    memory_overview_for_api,
    read_profile_for_api,
    save_fact,
    search_facts,
)

router = APIRouter(prefix="/api/agent-memory", tags=["agent-memory"])

logger = logging.getLogger("agent-tutor.agent-memory")

#: Catégories de faits autorisées ( source unique : le prompt de l'agent ).
ALLOWED_CATEGORIES = (
    "identity",
    "background",
    "personality",
    "preference",
    "interest",
)


def _require_service_secret(x_service_secret: Optional[str]) -> None:
    """Authentifie l'appelant service-à-service.

    Levée :
    - 503 si `AGENT_SERVICE_SECRET` n'est pas configurée (fermé par défaut)
    - 401 si l'en-tête est absent ou ne correspond pas.
    """
    expected = os.getenv("AGENT_SERVICE_SECRET", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "AGENT_SERVICE_SECRET non configurée — les routes /api/agent-memory "
                "sont désactivées ( l'agent vocal ne peut pas lire la mémoire )"
            ),
        )
    if not x_service_secret or not secrets.compare_digest(
        x_service_secret.strip(), expected
    ):
        raise HTTPException(
            status_code=401,
            detail="X-Service-Secret invalide",
        )


def _unavailable(exc: Exception, user_id: str) -> HTTPException:
    """Traduit une panne du store en 503 ( comme POST /api/livekit/agent/start ).

    Le store Postgres n'est pas une source de vérité optionnelle : sans lui
    l'agent démarrerait avec une mémoire vide **sans le savoir**, ce qui est
    pire qu'un échec franc.
    """
    logger.warning(
        "Mémoire indisponible pour user_id=%s : %s: %s",
        user_id,
        type(exc).__name__,
        exc,
    )
    return HTTPException(
        status_code=503,
        detail=(
            "Mémoire indisponible — le store Postgres est injoignable "
            f"( {type(exc).__name__} )"
        ),
    )


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------


@router.get("/{user_id}/profile")
def get_agent_profile(
    user_id: str,
    x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret"),
):
    """Profil longue durée — lu au démarrage de la session vocale."""
    _require_service_secret(x_service_secret)
    try:
        return read_profile_for_api(user_id)
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc, user_id)


@router.get("/{user_id}/overview")
def get_agent_overview(
    user_id: str,
    x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret"),
):
    """Profil **+** faits groupés par catégorie — un seul aller-retour.

    C'est exactement la forme attendue par
    `agent/config.py::build_system_instructions(profile, overview)`.
    """
    _require_service_secret(x_service_secret)
    try:
        return memory_overview_for_api(user_id)
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc, user_id)


@router.get("/{user_id}/facts")
def get_agent_facts(
    user_id: str,
    category: Optional[str] = None,
    x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret"),
):
    """Faits mémorisés, filtrés par catégorie si fourni."""
    _require_service_secret(x_service_secret)
    if category is not None and category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Catégorie inconnue : {category} "
                f"( attendu : {', '.join(ALLOWED_CATEGORIES)} )"
            ),
        )
    try:
        return {"user_id": user_id, "facts": list_facts(user_id, category=category)}
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc, user_id)


@router.get("/{user_id}/search")
def search_agent_memory(
    user_id: str,
    q: str,
    limit: int = Query(default=10, ge=1, le=50),
    x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret"),
):
    """Recherche de faits pertinents pour une requête ( limite 10 par défaut )."""
    _require_service_secret(x_service_secret)
    if not q.strip():
        raise HTTPException(status_code=422, detail="Le paramètre 'q' est requis")
    try:
        return {
            "user_id": user_id,
            "query": q,
            "facts": search_facts(user_id, q, limit=limit),
        }
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc, user_id)


# --------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------


class SaveFactRequest(BaseModel):
    """Corps de `POST /{user_id}/facts`."""

    category: str = Field(..., description="Une valeur de ALLOWED_CATEGORIES")
    content: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/{user_id}/facts")
def create_agent_fact(
    user_id: str,
    payload: SaveFactRequest,
    x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret"),
):
    """Enregistre un fait durable — `source="user"` ( déclaré explicitement )."""
    _require_service_secret(x_service_secret)

    if payload.category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Catégorie inconnue : {payload.category} "
                f"( attendu : {', '.join(ALLOWED_CATEGORIES)} )"
            ),
        )

    try:
        fact: dict[str, Any] = save_fact(
            user_id,
            payload.category,
            payload.content,
            source="user",
            confidence=payload.confidence,
        )
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc, user_id)

    return {"user_id": user_id, "fact": fact, "saved": True}