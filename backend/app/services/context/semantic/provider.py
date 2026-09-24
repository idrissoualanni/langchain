# EmbeddingProvider V7.1 (mission §7/§32).
#
# ABSTRACTION STABLE : le projet ne dépend d'AUCUNE technologie
# d'embeddings précise. Le provider par défaut est LOCAL et
# DÉTERMINISTE (aucun service externe obligatoire — mission §32 :
# « le premier provider peut rester local/existant »).
#
# LocalHashEmbeddingProvider :
#   - tokens normalisés (query_norm) + STEMS morphologiques
#     (variant_forms) → le texte « répéter/répétition » et le
#     topic « boucles » partagent des stems ;
#   - embedding = vecteur borné non négatif TF pondéré sur des
#     buckets de hachage stables (mêmes entrées → même vecteur,
#     testable §34) ;
#   - similarité COSINE encapsulée ICI (mission §7 : jamais
#     dispersée dans le code métier).
#
# Interchangeable : une implémentation ollama/cloud future
# implémente le même Protocol et s'installe via
# set_embedding_provider() — aucune autre ligne à changer.
# Providers : local-hash, ollama (local), cf-workers-ai
# (Cloudflare Workers AI — cloud gratuit, voir embeddings.yaml).
from __future__ import annotations

import math
import os
import threading
import time
from typing import Protocol

from app.config import OLLAMA_HOST, OLLAMA_API_KEY
from app.services.context.query_norm import (
    normalize_tokens,
    variant_forms,
)
from app.services.context.semantic.embedding_registry import (
    EmbeddingConfig,
    get_embedding_config,
)
from app.core.exceptions import (
    ModelTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)

# Dimension de l'embedding local (espace de hachage). Choisie
# pour limiter les collisions (12289 premier) tout en restant
# légère (léger > exact pour du ranking de candidats borné).
_HASH_DIM = 12289


class EmbeddingProvider(Protocol):
    """Contrat d'un fournisseur d'embeddings (mission §7)."""

    name: str

    def embed_text(self, text: str) -> list[float]:
        """texte → vecteur (même dimension pour tout le provider)."""
        ...


def _stable_hash(token: str) -> int:
    """Hachage STABLE entre process (pas de hash() Python randomisé)."""
    h = 2166136261
    for ch in token:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


class LocalHashEmbeddingProvider:
    """Provider local déterministe — zéro dépendance externe.

    Étapes (toutes GÉNÉRIQUES, aucun if subject/topic) :
      1. tokens normalisés (accents/casse/pluriels contrôlés) ;
      2. chaque token + ses variantes morphologiques ajoutées au
         vecteur (poids réduit pour les variantes) ;
      3. TF (fréquence) lissée par sqrt (fréquences trop raides
         écraseraient les phrases longues) ;
      4. normalisation L2 → cosine = produit scalaire direct.
    """

    name = "local-hash-v1"

    def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * _HASH_DIM
        vec = [0.0] * _HASH_DIM
        for tok in normalize_tokens(text):
            if len(tok) < 2:
                continue
            idx = _stable_hash("w:" + tok) % _HASH_DIM
            vec[idx] += 1.0
            # variantes morphologiques (pluriels FR/EN) — même
            # espace, poids moindre : la forme exacte prime.
            for v in variant_forms(tok):
                if v == tok or len(v) < 2:
                    continue
                vidx = _stable_hash("w:" + v) % _HASH_DIM
                vec[vidx] += 0.5
            # BIGRAMMES DE CARACTÈRES (§12) : rapprochent les
            # RACINES partageant une sous-chaîne — « recursivite »
            # et « recursion » partagent « recurs » ; « repetee »
            # et « repetition » partagent « repet ». Générique :
            # aucune paire de mots codée en dur.
            for i in range(len(tok) - 2):
                bg = "g:" + tok[i : i + 3]
                bidx = _stable_hash(bg) % _HASH_DIM
                vec[bidx] += 0.22
        # L2 normalisation
        norm = math.sqrt(sum(x * x for x in vec if x))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]


def cosine_similarity(
    a: list[float], b: list[float]
) -> float:
    """Similarité cosinus ENCAPSULÉE (mission §7) — unique point
    de calcul. Vecteurs de longueurs différentes → 0.0 (défense,
    jamais de crash)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    for x, y in zip(a, b):
        dot += x * y
    if dot <= 0.0:
        return 0.0
    # (vecteurs déjà L2-normalisés chez le provider local ; la
    # division défensive reste pour des providers externes)
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


class OllamaEmbeddingProvider:
    """Provider Ollama (référence V7.1 : Qwen3-Embedding 4B).

    Résolu depuis embeddings.yaml (registry) — le nom du modèle
    n'est JAMAIS écrit ici. Indisponible (service KO, modèle non
    pullé, timeout) → ProviderUnavailableError : le retriever
    sémantique devient unavailable et le routing retombe sur le
    lexical (fail-safe mission §15, addendum).
    """

    def __init__(self, config: EmbeddingConfig):
        self.name = f"ollama:{config.model or 'default'}"
        self._model = config.model
        self._timeout = float(config.options.get("timeout_s", 10))
        self._host = config.options.get("host", OLLAMA_HOST)
        self._api_key = config.options.get("api_key", OLLAMA_API_KEY)
        # num_ctx explicite : les phrases candidates/requêtes sont
        # courtes ; un ctx par défaut énorme fait échouer l'allocation
        # GPU (OOM Vulkan observé sur machine contrainte).
        self._num_ctx = int(config.options.get("num_ctx", 512))
        self._client = None

    def _get_client(self):
        if self._client is None:
            import ollama

            # Clé d'auth UNIQUEMENT vers un hôte distant — un
            # ollama LOCAL rejette un Bearer inattendu (401).
            # Règle générique sur l'hôte, aucune matière codée.
            host = (self._host or "").lower()
            is_local = any(
                h in host
                for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")
            )
            headers = (
                {"Authorization": f"Bearer {self._api_key}"}
                if self._api_key and not is_local
                else {}
            )
            self._client = ollama.Client(
                host=self._host, headers=headers
            )
        return self._client

    def embed_text(self, text: str) -> list[float]:
        """texte → embedding via client.embed(model, input).

        Timeout/404/500 transitoire/connexion →
        ProviderUnavailableError (état contrôlé, jamais de crash
        pipeline). Un 500 « out-of-memory during startup » est
        retenté une fois (allocation GPU transitoire fréquente).
        """
        try:
            return self._embed_once(text)
        except _TransientEmbedError:
            time.sleep(0.6)
            try:
                return self._embed_once(text)
            except _TransientEmbedError as exc:
                raise ProviderUnavailableError(
                    f"ollama embeddings indisponible: {exc}"
                ) from exc
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise self._wrap(exc)

    def _embed_once(self, text: str) -> list[float]:
        try:
            client = self._get_client()
            resp = client.embed(
                model=self._model,
                input=text or " ",
                options={"num_ctx": self._num_ctx},
            )
            embs = (
                resp.get("embeddings")
                if isinstance(resp, dict)
                else getattr(resp, "embeddings", None)
            )
            if not embs:
                raise ProviderUnavailableError(
                    "réponse embeddings vide",
                )
            return list(embs[0])
        except _TransientEmbedError:
            raise
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            msg = str(exc)
            transient = (
                "500" in msg
                or "out-of-memory" in msg.lower()
                or "terminated" in msg.lower()
            )
            if transient:
                raise _TransientEmbedError(msg)
            raise self._wrap(exc)

    def _wrap(self, exc: Exception) -> Exception:
        msg = str(exc)
        if (
            "timeout" in msg.lower()
            or "timed out" in msg.lower()
        ):
            return ModelTimeoutError(
                f"embedding timeout ({self._timeout}s)"
            )
        if "not found" in msg.lower() or "404" in msg:
            return ProviderUnavailableError(
                f"modèle '{self._model}' non pullé"
            )
        return ProviderUnavailableError(
            f"ollama embeddings indisponible: {msg}"
        )


class _TransientEmbedError(Exception):
    """Erreur transitoire (500/OOM) — retentée une fois."""


class CloudflareWorkersAIEmbeddingProvider:
    """Provider CLOUD GRATUIT — Cloudflare Workers AI (REST).

    Résolu depuis embeddings.yaml (provider_type: cf-workers-ai).
    Free tier : 10 000 neurons/jour (bge-m3 = 1075 neurons / M
    input tokens). Modèles multilingues FR+EN (@cf/baai/bge-m3,
    @cf/qwen/qwen3-embedding-0.6b) — contrairement aux
    @cf/baai/bge-*-en-v1.5 (anglais seul).

    SÉCURITÉ : AUCUNE clé en clair. Le token API vient de l'env
    (nom lu dans options.api_token_env, défaut CLOUDFLARE_API_TOKEN)
    — jamais du YAML. L'account_id vient de options.account_id ou
    de l'env CLOUDFLARE_ACCOUNT_ID.

    Indisponible (401/403 token, 404 modèle, 429 quota, timeout,
    connexion) → ProviderUnavailableError / RateLimitError /
    ModelTimeoutError : le retriever passe unavailable et le
    routing retombe sur le lexical (même fail-safe qu'ollama §15).
    """

    _API_BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, config: EmbeddingConfig):
        self.name = f"cf-workers-ai:{config.model or 'default'}"
        self._model = config.model
        self._timeout = float(config.options.get("timeout_s", 15))
        # account_id : option YAML > env. Vide autorisé (env).
        self._account_id = (
            config.options.get("account_id", "").strip()
            or os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        )
        env_var = (
            config.options.get("api_token_env", "")
            or "CLOUDFLARE_API_TOKEN"
        )
        # Le NOM de l'env var est dans le YAML ; la VALEUR jamais.
        self._api_token = os.getenv(env_var, "").strip()
        base = (
            config.options.get("endpoint", "").strip()
            or self._API_BASE
        ).rstrip("/")
        self._url = (
            f"{base}/accounts/{self._account_id}/ai/run/{self._model}"
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    def _classify(self, status: int, msg: str) -> Exception:
        """Code HTTP → exception contrôlée (hiérarchie §16)."""
        if status in (401, 403):
            return ProviderUnavailableError(
                "Cloudflare: token invalide/insuffisant (vérifiez "
                "CLOUDFLARE_API_TOKEN, scope 'Workers AI Read')"
            )
        if status == 404:
            return ProviderUnavailableError(
                f"modèle '{self._model}' indisponible sur ce compte "
                "(vérifiez CLOUDFLARE_ACCOUNT_ID)"
            )
        if status == 429:
            return RateLimitError(
                "quota Workers AI atteint (free tier : "
                "10 000 neurons/jour)"
            )
        if status >= 500:
            # transitoire côté Cloudflare → retenté par embed_text
            return _TransientEmbedError(f"HTTP {status}: {msg}")
        return ProviderUnavailableError(
            f"Cloudflare embeddings indisponible (HTTP {status}): {msg}"
        )

    def _extract(self, payload) -> list[float]:
        """Réponse CF v4 → 1er vecteur (data = [[...]] dans result).

        CF v4 enveloppe le résultat dans « result » ; on accepte
        aussi une réponse nue pour rester robuste.
        """
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("réponse Cloudflare illisible")
        if payload.get("success") is False:
            errs = payload.get("errors") or []
            code = errs[0].get("code") if errs else None
            msg = errs[0].get("message", "") if errs else "inconnu"
            # code 7000041 = quota dépassé (free tier) → RateLimit
            if code in (7000041, 7000042) or "limit" in str(msg).lower():
                return RateLimitError(f"quota Workers AI: {msg}")
            return ProviderUnavailableError(f"Cloudflare erreur {code}: {msg}")
        data = payload.get("data")
        # enveloppe v4 : le vrai payload est sous « result »
        if data is None:
            data = (payload.get("result") or {}).get("data")
        if not data or not isinstance(data, list):
            raise ProviderUnavailableError("réponse embeddings vide")
        vec = data[0]
        if not isinstance(vec, (list, tuple)) or not vec:
            raise ProviderUnavailableError("vecteur embedding vide")
        return [float(x) for x in vec]

    def _embed_once(self, text: str) -> list[float]:
        import requests  # dépendance déjà déclarée (requirements.txt)

        try:
            resp = requests.post(
                self._url,
                json={"text": text or " "},
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise ModelTimeoutError(
                f"embedding timeout ({self._timeout}s)"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUnavailableError(
                f"Cloudflare injoignable: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise self._classify(
                resp.status_code,
                (resp.text or "")[:200],
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderUnavailableError(
                "réponse non-JSON de Cloudflare"
            ) from exc
        return self._extract(payload)

    def embed_text(self, text: str) -> list[float]:
        """texte → embedding via REST Workers AI.

        Un 5xx (transitoire) est retenté une fois (même politique
        qu'ollama) ; tout échec devient une exception contrôlée de
        la hiérarchie §16 — jamais une exception brute vers le
        pipeline (fail-safe retriever §15).
        """
        if not self._account_id:
            raise ProviderUnavailableError(
                "CLOUDFLARE_ACCOUNT_ID manquant (env ou option YAML)"
            )
        if not self._api_token:
            raise ProviderUnavailableError(
                "CLOUDFLARE_API_TOKEN manquant (env) — créez un token "
                "avec le scope 'Workers AI Read' sur "
                "https://dash.cloudflare.com/profile/api-tokens"
            )
        try:
            return self._embed_once(text)
        except _TransientEmbedError:
            time.sleep(0.6)
            try:
                return self._embed_once(text)
            except _TransientEmbedError as exc:
                raise ProviderUnavailableError(
                    f"Cloudflare embeddings indisponible: {exc}"
                ) from exc
        except (ProviderUnavailableError, ModelTimeoutError, RateLimitError):
            raise
        except Exception as exc:
            raise ProviderUnavailableError(
                f"Cloudflare embeddings indisponible: {exc}"
            ) from exc


# ------------------------------------------------------------------
# Provider actif — résolu par la registry (embeddings.yaml),
# thread-safe, ré-installable (tests §25, providers externes)
# ------------------------------------------------------------------
_provider_lock = threading.RLock()
_active_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Provider actif depuis embeddings.yaml (addendum).

    ollama (référence 4B) par défaut ; cf-workers-ai (cloud
    gratuit Cloudflare, activable par EMBEDDING_PROVIDER) ;
    local-hash si YAML vide. L'instance est MAINTENUE : le client
    est réutilisé entre appels (pas de reconnexion par requête).
    """
    global _active_provider
    with _provider_lock:
        if _active_provider is None:
            cfg = get_embedding_config()
            if cfg.provider_type == "ollama":
                _active_provider = OllamaEmbeddingProvider(cfg)
            elif cfg.provider_type == "cf-workers-ai":
                _active_provider = (
                    CloudflareWorkersAIEmbeddingProvider(cfg)
                )
            else:
                _active_provider = LocalHashEmbeddingProvider()
        return _active_provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Installe/remplace le provider (tests, providers externes).

    None → re-résolution depuis la registry au prochain accès.
    """
    global _active_provider
    with _provider_lock:
        _active_provider = provider


__all__ = [
    "EmbeddingProvider",
    "LocalHashEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "CloudflareWorkersAIEmbeddingProvider",
    "cosine_similarity",
    "get_embedding_provider",
    "set_embedding_provider",
]
