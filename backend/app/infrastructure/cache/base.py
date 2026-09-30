# Contrat de cache — mémoire (TTLCache) ou Redis (ADR-019, ADR-006bis).
#
# Pourquoi un contrat et pas une classe concrète : le backend doit être
# interchangeable sans toucher aux appelants. Le bug qui motive Redis
# ( ADR-006bis ) est structurel : l'API et le worker vocal sont DEUX
# processus ( render.yaml ), chacun avec son TTLCache privé — une
# invalidation côté API ne touche pas le worker, qui sert un profil
# périmé jusqu'à 5 minutes.
#
# Règles du contrat :
#   - Une valeur `None` n'est JAMAIS stockée ( `get` ne peut pas
#     distinguer « absent » de « None mis en cache » — même piège que
#     le bug `get_or` supprimé de TTLCache ).
#   - Les valeurs sont JSON-sérialisables ( dict, list, str, nombre,
#     bool ). Pas d'objets arbitraires.
#   - Un backend peut échouer ( Redis injoignable ) : il retourne None
#     et n'écrit rien — le cache n'est PAS une source de vérité,
#     seulement une optimisation de latence.
import abc
from typing import Any


class CacheBackend(abc.ABC):
    """Interface commune aux backends mémoire et Redis."""

    @abc.abstractmethod
    def get(self, key: str) -> Any | None:
        """Valeur pour `key`, None si absente/expirée/échec backend."""

    @abc.abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Stocker `value` pour `key`. ttl_seconds remplace la TTL
        par défaut du backend si fourni ; None est ignoré ( jamais
        mis en cache )."""

    @abc.abstractmethod
    def invalidate(self, key: str) -> None:
        """Retirer `key` du cache."""

    @abc.abstractmethod
    def clear_prefix(self, prefix: str) -> int:
        """Retirer toutes les clés commençant par `prefix`.

        Retourne le nombre de clés supprimées ( 0 si absent ).
        Retourner un compte est utile aux appels qui veulent logguer
        l'invalidation ( ex. purge d'un utilisateur )."""


__all__ = ["CacheBackend"]