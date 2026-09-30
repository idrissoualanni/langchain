# Fabrique du backend de cache ( ADR-006bis, ADR-019 ).
#
# REDIS_URL défini ET package `redis` installé  → RedisBackend
# sinon                                      → TTLCache ( mémoire )
#
# Le repli est silencieux mais LOGGUÉ : le cache n'est pas une source
# de vérité. Une URL Redis configurée mais injoignable fait retomber
# les lectures en None et les écritures en no-op ( jamais une
# exception dans le chemin appelant ).
#
# Pas de ping au démarrage : dans docker compose, `redis` peut
# démarrer après l'API ( depends_on: service_healthy ne garantit pas
# l'ordre au boot en pratique ). La paresse du premier appel suffit.
import logging
import os

from app.infrastructure.cache.base import CacheBackend
from app.infrastructure.cache.redis_backend import RedisBackend, _REDIS_AVAILABLE
from app.infrastructure.cache.ttl import TTLCache

logger = logging.getLogger(__name__)


def get_cache(
    ttl_seconds: int = 300,
    prefix: str = "",
    max_entries: int = 1000,
) -> CacheBackend:
    """Retourne le backend de cache de l'application.

    `prefix` ( optionnel ) est préfixé à TOUTES les clés Redis — utile
    pour isoler deux environnements sur le même Redis ( ex. `prod:` ).
    Le backend mémoire TTLCache ignore le prefix : ses clés contiennent
    déjà leur espace de noms ( ex. `mem:{user_id}:profile` ).
    """
    url = os.getenv("REDIS_URL", "").strip()
    if url and _REDIS_AVAILABLE:
        try:
            backend = RedisBackend(url=url, ttl_seconds=ttl_seconds, prefix=prefix)
            logger.info("Cache : Redis actif ( REDIS_URL présente, redis-py installé )")
            return backend
        except Exception as exc:  # pragma: no cover — dépend de l'environnement
            logger.warning("Cache : RedisBackend non initialisé ( %s ) — repli mémoire", exc)
    elif url:
        logger.warning(
            "Cache : REDIS_URL définie mais package 'redis' absent — repli cache mémoire"
        )
    return TTLCache(ttl_seconds=ttl_seconds, max_entries=max_entries)


__all__ = ["get_cache"]