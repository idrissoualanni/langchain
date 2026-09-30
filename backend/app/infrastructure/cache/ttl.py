# Cache TTL in-process — invalidation manuelle par clé.
#
# C'est le backend MÉMOIRE du contrat CacheBackend ( ADR-019 ). Il est
# utilisé quand aucune URL Redis n'est configurée ( REDIS_URL absente
# ou package `redis` absent — voir factory.get_cache ).
#
# POURQUOI : ce projet a des lectures SQL synchrones répétées sur des
# données qui changent RAREMENT — typiquement la mémoire longue durée
# de l'utilisateur, relue à chaque entrée de session vocale
# ( app.infrastructure.livekit.agent._build_instructions_async ).
# Un cache in-process supprime ces aller-retours sans ajouter de
# dépendance.
#
# LIMITE STRUCTURELLE ( à l'origine du passage Redis, ADR-006bis ) :
# ce cache est PRIVÉ à un process. Or render.yaml déploie DEUX
# services depuis la même image ( API + worker vocal ) : une
# invalidation côté API ne touche pas le worker, qui sert un profil
# périmé jusqu'à la TTL. Redis ( backend partagé ) corrige ça.
#
# COHÉRENCE : ce cache n'est PAS un cache de résultats calculés. Il ne
# s'applique qu'à des données lues via UNE fonction, et écrites via des
# fonctions qui INVALIDENT explicitement ( voir memory.py ). La TTL est
# la sécurité ultime : une invalidation oubliée se cicatrise d'elle-même.
from __future__ import annotations

import threading
import time
from typing import Any

from app.infrastructure.cache.base import CacheBackend


class TTLCache(CacheBackend):
    """Cache clé → valeur avec expiration par clé.

    Thread-safe ( verrou global ) : FastAPI dispatche les handlers
    synchrones dans un threadpool, et log_event publie depuis des
    executors — plusieurs threads peuvent lire/écrire le même cache.

    Pas de nettoyage proactif : les entrées expirées sont éliminées
    paresseusement à la lecture ( pas de thread de background à
    maintenir, et la collection bornée évite la croissance infinie ).
    """

    def __init__(
        self,
        ttl_seconds: float = 300,
        max_entries: int = 1000,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds doit être positif")
        if max_entries <= 0:
            raise ValueError("max_entries doit être positif")

        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Retourne la valeur si présente et non expirée, sinon None.

        La valeur None n'est jamais stockée ( contrat CacheBackend ) :
        « absent » et « None » sont indiscernables par design.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                # Expiration paresseuse
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Écrit une entrée avec la TTL du cache.

        `ttl_seconds` ( optionnel ) remplace la TTL par défaut pour
        CETTE entrée. None est ignoré — jamais mis en cache.
        """
        if value is None:
            return
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        with self._lock:
            if len(self._store) >= self._max_entries and key not in self._store:
                # Éviction : la plus ancienne entrée ( insertion order du
                # dict, pas strictement LRU — suffisant pour borner ).
                oldest = next(iter(self._store), None)
                if oldest is not None:
                    del self._store[oldest]
            self._store[key] = (time.monotonic() + ttl, value)

    def invalidate(self, key: str) -> None:
        """Invalide UNE clé. Inexistant = no-op silencieux."""
        with self._lock:
            self._store.pop(key, None)

    def clear_prefix(self, prefix: str) -> int:
        """Invalide toutes les clés commençant par prefix.

        Retourne le nombre de clés supprimées. Typiquement
        clear_prefix(f"user:{user_id}:") pour tout invalider.
        """
        if not prefix:
            return 0
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
        return len(keys)

    def clear(self) -> None:
        """Invalide tout ( tests, health checks )."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


__all__ = ["TTLCache"]
