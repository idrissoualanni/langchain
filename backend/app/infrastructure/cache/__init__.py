# Cache — contrat + backends ( ADR-019, ADR-006bis ).
#
# Le point d'entrée est factory.get_cache : il choisit Redis quand
# REDIS_URL est définie et redis-py installé, sinon le cache mémoire
# TTLCache. Le contrat CacheBackend est l'interface que les services
# ( ex. services.memory ) manipulent — jamais une classe concrète.
from app.infrastructure.cache.base import CacheBackend
from app.infrastructure.cache.factory import get_cache
from app.infrastructure.cache.redis_backend import RedisBackend
from app.infrastructure.cache.ttl import TTLCache

__all__ = ["CacheBackend", "get_cache", "TTLCache", "RedisBackend"]