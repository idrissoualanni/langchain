# Backend Redis pour CacheBackend ( ADR-006bis ).
#
# Implémentation choisie : redis-py ( le client officiel ), valable
# aussi bien pour un Redis local ( docker compose, service `redis` )
# que pour un Redis managé exposant une URL redis:// ou rediss://
# ( Upstash, Layerbase... — mêmes URL, même protocole ).
#
# L'import de `redis` est paresseux : si le package n'est pas installé,
# RedisBackend ne peut pas exister. C'est factory.get_cache qui décide
# ( REDIS_URL défini ET package présent → Redis ; sinon → TTLCache ).
# Le repli est donc silencieux MAIS loggué : le cache n'est pas une
# source de vérité, une panne Redis ne doit pas faire tomber l'API.
#
# Règles du contrat ( base.py ) :
#   - valeurs JSON-sérialisables ( dict, list, str, nombre, bool )
#   - None jamais stocké
#   - échec Redis → get() retourne None, set() n'écrit rien
#   - erreurs logguées AU PLUS une fois par type toutes les 60 s
#     ( un Redis down ne doit pas spamer les logs à chaque lecture ).
import json
import logging
import time
from typing import Any

from app.infrastructure.cache.base import CacheBackend

try:
    import redis as _redis_lib  # type: ignore[import-not-found]
except Exception:  # pragma: no cover — dépend de l'environnement
    _redis_lib = None  # type: ignore[assignment]
_REDIS_AVAILABLE = _redis_lib is not None

logger = logging.getLogger(__name__)

# Throttle des erreurs : dernier horodatage ( monotonic ) par opération.
_last_error_at: dict[str, float] = {}
_ERROR_LOG_INTERVAL = 60.0


def _log_once(op: str) -> None:
    now = time.monotonic()
    if now - _last_error_at.get(op, 0.0) < _ERROR_LOG_INTERVAL:
        return
    _last_error_at[op] = now
    logger.warning(
        "CacheBackend Redis : échec %s (Redis injoignable ?). "
        "Repli lecture None / écriture ignorée — le cache n'est pas une source de vérité.",
        op,
    )


class RedisBackend(CacheBackend):
    """CacheBackend posé sur Redis via redis-py."""

    def __init__(
        self,
        url: str,
        ttl_seconds: int = 300,
        prefix: str = "",
        socket_timeout: float = 0.5,
    ) -> None:
        if not _REDIS_AVAILABLE:
            raise RuntimeError(
                "Le package 'redis' n'est pas installé ( pip install redis>=5.0 )"
            )
        self._ttl = ttl_seconds
        self._prefix = prefix
        # decode_responses=True : get() renvoie str ( pas bytes ) — on
        # JSON-encode nous-mêmes, donc pas besoin du codec redis.
        self._client = _redis_lib.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
            retry_on_timeout=True,
        )

    def _raw(self, key: str) -> str:
        return f"{self._prefix}{key}" if self._prefix else key

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(self._raw(key))
        except Exception:
            _log_once("get")
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            _log_once("decode")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if value is None:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            logger.warning(
                "CacheBackend Redis : valeur non JSON-sérialisable pour %s — non mise en cache.",
                key,
            )
            return
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        try:
            if ttl > 0:
                self._client.setex(self._raw(key), ttl, payload)
            else:
                self._client.set(self._raw(key), payload)
        except Exception:
            _log_once("set")

    def invalidate(self, key: str) -> None:
        try:
            self._client.delete(self._raw(key))
        except Exception:
            _log_once("delete")

    def clear_prefix(self, prefix: str) -> int:
        """Supprime toutes les clés commençant par `prefix`.

        SCAN + DELETE par lots ( le cache est borné par les TTL, donc
        le nombre de clés reste raisonnable ). Retourne le nombre de
        clés supprimées ; -1 si Redis était injoignable ( l'appelant
        ne peut pas distinguer « 0 » d'un échec autrement ).
        """
        if not prefix:
            return 0
        try:
            pattern = f"{self._prefix}{prefix}*"
            total = 0
            cursor = 0
            while True:
                cursor, keys = self._client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    total += len(keys)
                    self._client.delete(*keys)
                if cursor == 0:
                    break
            return total
        except Exception:
            _log_once("clear_prefix")
            return -1


__all__ = ["RedisBackend", "_REDIS_AVAILABLE"]