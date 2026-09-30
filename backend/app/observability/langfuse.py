"""Langfuse observability — module unique centralisant le SDK.

Règles du projet (ADR Langfuse) :
- Tout le code Langfuse vit ICI ; le reste de l'app ne connaît que
  `get_callbacks`, `invoke_config` et `shutdown_langfuse`.
- Résilience d'abord : si le package `langfuse` n'est pas installé,
  si `LANGFUSE_ENABLED` est faux, ou si les clés / l'URL sont absentes,
  toutes les fonctions retournent des équivalents « no-op » :
  liste de callbacks VIDE, config d'invoke inchangée, flush silencieux.
  Une panne Langfuse ne doit jamais faire échouer (ni ralentir) une
  requête de l'agent.
- Confidentialité : le client est créé avec une fonction `mask` qui
  masque les valeurs sensibles (Authorization, JWT, mots de passe,
  clés API…). L'identité tracée est un user_id INTERNE + session_id
  (thread_id) — jamais l'email.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import langfuse_settings

logger = logging.getLogger(__name__)

# Clients Langfuse : une seule instance par process (créée paresseusement
# au premier appel réellement utile, uniquement si la config est valide).
_client: Any = None


# ---------------------------------------------------------------------------
# Masquage des valeurs sensibles (utilisé comme `mask` du client SDK)
# ---------------------------------------------------------------------------

# Clés dont la VALEUR est systématiquement masquée (comparaison en minuscules,
# sous-chaîne pour couvrir Authorization, X-Api-Key, Set-Cookie, …).
_SENSITIVE_KEY_MARKERS = (
    "password",
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "token",
    "jwt",
    "cookie",
)

# Clés dont le NOM seul doit disparaître des sorties (contexte d'entête HTTP).
_REDACTED_KEY_MARKERS = (
    "authorization",
    "x-api-key",
    "cookie",
    "set-cookie",
)


def mask_payload(payload: Any) -> Any:
    """Masque récursivement les valeurs sensibles d'un payload.

    Utilisée par le client Langfuse (paramètre ``mask``) : le payload
    n'est jamais transmis en clair pour les clés sensibles.
    """
    if isinstance(payload, list):
        return [mask_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(mask_payload(item) for item in payload)
    if isinstance(payload, dict):
        masked: dict[str, Any] = {}
        for key, value in payload.items():
            key_lower = str(key).lower()
            if any(marker in key_lower for marker in _SENSITIVE_KEY_MARKERS):
                # La clé est sensible : on masque la valeur, mais on
                # conserve la structure (le payload reste exploitable).
                masked[key] = "***"
            elif any(marker in key_lower for marker in _REDACTED_KEY_MARKERS):
                continue  # entête HTTP : on supprime la clé elle-même
            elif isinstance(value, (dict, list, tuple)):
                masked[key] = mask_payload(value)
            else:
                masked[key] = value
        return masked
    if isinstance(payload, str):
        # Chaîne isolée : on ne peut pas savoir si elle est sensible ;
        # on la laisse (c'est le rôle du mask au niveau des clés).
        return payload
    return payload


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Langfuse est utilisable si activé ET si clés + URL sont présentes.

    Le SDK lit aussi ses variables d'environnement, mais on garde la
    source de vérité dans la config applicative pour rester testable.
    """
    settings = langfuse_settings()
    return bool(
        settings.enabled
        and settings.public_key
        and settings.secret_key
        and settings.base_url
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def get_client() -> Any:
    """Client Langfuse lazy (None si inutilisable). Crée le singleton au
    premier appel : le CallbackHandler LangChain récupère ensuite CE client
    via ``langfuse.get_client()``.
    """
    global _client
    if _client is not None:
        return _client
    if not is_enabled():
        return None
    try:
        from langfuse import Langfuse

        settings = langfuse_settings()
        _client = Langfuse(
            public_key=settings.public_key,
            secret_key=settings.secret_key,
            base_url=settings.base_url,
            mask=mask_payload,
        )
    except Exception:  # package absent, import cassé, …
        logger.warning("Langfuse indisponible : tracing désactivé", exc_info=True)
        _client = None
    return _client


# ---------------------------------------------------------------------------
# Interface utilisée par le runner / les routes
# ---------------------------------------------------------------------------


def get_callbacks() -> list[Any]:
    """Callbacks LangChain à brancher sur l'invoke du graphe.

    Retourne une liste VIDE si Langfuse est désactivé, si les clés/URL
    manquent, ou si le package n'est pas installé. Un handler FRAIS est
    créé à chaque appel : le passage d'un handler réutilisé en
    concurrence peut corrompre last_trace_id (doc SDK).
    """
    if not is_enabled():
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception:
        logger.warning("Impossible de créer le callback Langfuse", exc_info=True)
        return []


def trace_metadata(user_id: str = "", session_id: str = "") -> dict[str, Any]:
    """Métadonnées Langfuse pour ``config={"metadata": {...}}`` de l'invoke.

    Identifiants INTERNES (jamais l'email) : user_id applicatif (UUID) et
    thread_id comme session Langfuse.
    """
    if not is_enabled():
        return {}
    metadata: dict[str, Any] = {}
    if user_id:
        metadata["langfuse_user_id"] = user_id
    if session_id:
        metadata["langfuse_session_id"] = session_id
    return metadata


def invoke_config(
    config: dict[str, Any], user_id: str = "", session_id: str = ""
) -> dict[str, Any]:
    """Enrichit la config d'invoke avec callbacks + metadata Langfuse.

    Retourne ``config`` INCHANGÉ (même objet) si Langfuse est inutilisable :
    l'appel du graphe a exactement le comportement actuel. Ne mute jamais
    la config passée en entrée (la config de base reste utilisée par
    get_state / get_state_history après l'invoke).
    """
    callbacks = get_callbacks()
    if not callbacks:
        return config
    return {
        **config,
        "callbacks": callbacks,
        "metadata": {
            **trace_metadata(user_id, session_id),
            # Les tags aident au filtrage dans l'UI Langfuse.
            "langfuse_tags": ["agent-tutor"],
        },
    }


def shutdown_langfuse() -> None:
    """Vide la file d'export synchroniquement (à l'arrêt du serveur).

    Ne lève JAMAIS : à l'arrêt on ne bloque pas la sortie du process.
    """
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
        logger.info("Langfuse : file d'export vidée")
    except Exception:
        logger.warning("Langfuse : échec du flush final (ignoré)", exc_info=True)