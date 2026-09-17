# Exceptions V7.1 — hiérarchie UNIFIÉE (mission §16).
#
# PRINCIPE : UN seul système d'exceptions pour tout le backend.
# Aucune exception métier concurrente n'est créée : les modules
# existants qui catchent déjà Exception (middleware wrap_tool_call,
# engine decide, builder) continuent de fonctionner — cette
# hiérarchie DONNE un TYPE aux erreurs pour observabilité et
# décision de fallback, sans changer le flux de gestion.
#
# Hiérarchie (adaptée aux conventions V5-V7 du projet) :
#
#   AppError
#   ├── RoutingError
#   ├── RetrievalError
#   │   ├── KnowledgeRetrievalError
#   │   ├── SemanticRetrievalError
#   │   └── WebSearchError
#   ├── MemoryError_ (nom évité : memory_error préfixe utile)
#   ├── LearningError
#   ├── ToolError
#   ├── ModelError
#   │   ├── ProviderUnavailableError
#   │   ├── ModelTimeoutError
#   │   └── RateLimitError
#   └── ResponseError
#
# ROBUSTESSE (mission §17) : aucun de ces types ne doit jamais
# provoquer un 500 non contrôlé — chaque site d'appel les convertit
# en état contrôlé (status "error" / fallback lexical / ToolMessage
# d'erreur) et logge la cause technique.
from __future__ import annotations


class AppError(Exception):
    """Racine de toutes les erreurs métier de l'application."""

    #: code court utilisé dans les logs/observabilité (jamais de secret)
    code: str = "app_error"

    def __init__(self, message: str = "", *, cause: Exception | None = None):
        self.cause = cause
        super().__init__(message or self.__class__.__name__)

    def detail(self) -> str:
        """Représentation loggable (sans secret) — utilisée par log_event."""
        msg = str(self)
        base = f"[{self.code}] {msg}" if msg else f"[{self.code}]"
        if self.cause is not None:
            base += f" | cause={type(self.cause).__name__}: {self.cause}"
        return base[:300]


class RoutingError(AppError):
    """Erreur de classification (router)."""

    code = "routing_error"


class RetrievalError(AppError):
    """Erreur de récupération de contenu (knowledge/web/semantic)."""

    code = "retrieval_error"


class KnowledgeRetrievalError(RetrievalError):
    """Lecture/scoring knowledge local impossible."""

    code = "knowledge_retrieval_error"


class SemanticRetrievalError(RetrievalError):
    """Couche sémantique en échec (embedding/recherche)."""

    code = "semantic_retrieval_error"


class WebSearchError(RetrievalError):
    """Recherche web en échec technique."""

    code = "web_search_error"


class AppMemoryError(AppError):
    """Mémoire longue durée inaccessible (store SQLite)."""

    code = "memory_error"


class LearningError(AppError):
    """Learning Profile / Learning Engine en échec."""

    code = "learning_error"


class ToolError(AppError):
    """Exécution d'un tool en échec."""

    code = "tool_error"


class ModelError(AppError):
    """Provider LLM en échec."""

    code = "model_error"


class ProviderUnavailableError(ModelError):
    """Provider LLM/embedding joignable mais indisponible."""

    code = "provider_unavailable"


class ModelTimeoutError(ModelError):
    """Timeout d'appel provider."""

    code = "model_timeout"


class RateLimitError(ModelError):
    """Quota/rate limit du provider."""

    code = "rate_limit"


class ResponseError(AppError):
    """Normalisation/construction de la réponse en échec."""

    code = "response_error"


__all__ = [
    "AppError",
    "RoutingError",
    "RetrievalError",
    "KnowledgeRetrievalError",
    "SemanticRetrievalError",
    "WebSearchError",
    "AppMemoryError",
    "LearningError",
    "ToolError",
    "ModelError",
    "ProviderUnavailableError",
    "ModelTimeoutError",
    "RateLimitError",
    "ResponseError",
]
