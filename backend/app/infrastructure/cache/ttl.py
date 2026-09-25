# Cache TTL in-process — invalidation manuelle par clé.
#
# POURQUOI : ce projet ( plan Render free, un seul process, pas de
# Redis ) a des lectures SQL synchrones répétées sur des données qui
# changent RAREMENT — typiquement la mémoire longue durée de
# l'utilisateur, relue à chaque entrée de session vocale
# ( app.infrastructure.livekit.agent._build_instructions_async ).
# Un cache in-process supprime ces aller-retours sans ajouter de
# dépendance.
#
# POURQUOI PAS Redis : aucun gain tant qu'il n'y a qu'un process ; et
# le plan free ne le justifie pas. L'interface get/set/invalidate est
# COMPATIBLE avec un backend Redis futur — la migration sera un
# changement d'implémentation, pas d'API.
#
# COHÉRENCE : ce cache n'est PAS un cache de résultats calculés. Il ne
# s'applique qu'à des données lues via UNE fonction, et écrites via des
# fonctions qui INVALIDENT explicitement ( voir memory.py ). La TTL est
# la sécurité ultime : une invalidation oubliée se cicatrise d'elle-même.
from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
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

        ⚠ None EST aussi une valeur légitime possible : distinguer
        « absent » de « None caché » via get_or() si nécessaire.
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

    def get_or(self, key: str, default: Any = None) -> Any:
        """Comme get, mais `default` si absent/expiré."""
        return self.get(key) if self.get(key) is not None else default

    def set(self, key: str, value: Any) -> None:
        """Écrit une entrée avec la TTL du cache."""
        with self._lock:
            if len(self._store) >= self._max_entries and key not in self._store:
                # Éviction : la plus ancienne entrée ( insertion order du
                # dict, pas strictement LRU — suffisant pour borner ).
                oldest = next(iter(self._store), None)
                if oldest is not None:
                    del self._store[oldest]
            self._store[key] = (time.monotonic() + self._ttl, value)

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
