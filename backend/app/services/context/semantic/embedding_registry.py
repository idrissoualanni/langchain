# Embedding Registry V7.1 (ADDENDUM — modèle d'embeddings).
#
# SOURCE DÉCLARATIVE UNIQUE des embeddings : app/embeddings.yaml.
# AUCUN nom de modèle écrit en dur dans le code métier (mission
# §24 + addendum). Le provider actif vient de l'env
# (EMBEDDING_PROVIDER), le modèle par défaut du YAML — jamais
# trois sources contradictoires (convention models.yaml V6.8 §38).
#
# Format YAML (voir app/embeddings.yaml) :
#   active: ollama            # provider actif
#   providers:
#     local-hash: {...}       # hash local, zéro service externe
#     ollama:
#       provider_type: ollama
#       model: qwen3-embedding:4b     # modèle de RÉFÉRENCE V7.1
#       dim: 2560
#       timeout_s: 10
#     # bge-m3, qwen3-embedding:0.6b, qwen3-embedding:8b, un
#     # provider externe... : ajouter UNE entrée, zéro code.
#
# RÉSOLUTION : get_embedding_config() → (name, type, model, opts)
#   - env EMBEDDING_PROVIDER=* nomme le provider actif ;
#   - entrée YAML inconnue → fallback documenté local-hash
#     (fail-safe §15 : PAS de crash, lexical fallback assuré).
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.logging.events import log_event

# REFACTOR : embeddings.yaml vit à la racine du package app/ ;
# ce fichier est dans app/services/context/semantic/ → parents[3]=app.
_EMBEDDINGS_YAML = (
    Path(__file__).resolve().parents[3] / "embeddings.yaml"
)

_cache: dict | None = None


@dataclass
class EmbeddingConfig:
    """Config résolue d'UN provider d'embeddings."""

    name: str                      # clé YAML (ex: ollama)
    provider_type: str             # type d'implémentation (ollama/local-hash)
    model: str = ""                 # nom du modèle (vide pour local-hash)
    dim: int | None = None
    options: dict = field(default_factory=dict)


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_EMBEDDINGS_YAML, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:
        log_event(
            "EMBEDDING_REGISTRY_ERROR",
            level="ERROR",
            message=f"embeddings.yaml illisible ({exc}) — fallback local-hash",
        )
        data = {}
    _cache = data
    return data


def invalidate_embedding_cache() -> None:
    """Force le rechargement (tests)."""
    global _cache
    _cache = None


def get_embedding_config(
    provider_name: str | None = None,
    path: Path | None = None,
) -> EmbeddingConfig:
    """Résout la config d'embeddings active (déclarative).

    Priorité : provider_name > env EMBEDDING_PROVIDER > YAML active.
    Entrée inconnue ou YAML vide → local-hash (honnête, loggé).
    """
    if path is not None:
        # lecture ponctuelle (tests) sans polluer le cache
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            data = {}
    else:
        data = _load()

    providers = data.get("providers", {}) or {}
    name = (
        provider_name
        or os.getenv("EMBEDDING_PROVIDER", "")
        or data.get("active", "")
        or "local-hash"
    )
    entry = providers.get(name)
    if not isinstance(entry, dict):
        log_event(
            "EMBEDDING_PROVIDER_FALLBACK",
            level="WARNING",
            message=(
                f"Embedding provider '{name}' inconnu — "
                "fallback local-hash"
            ),
        )
        return EmbeddingConfig(
            name="local-hash",
            provider_type="local-hash",
        )
    return EmbeddingConfig(
        name=name,
        provider_type=entry.get("provider_type", name),
        model=entry.get("model", ""),
        dim=entry.get("dim"),
        options={
            k: v
            for k, v in entry.items()
            if k not in ("provider_type", "model", "dim")
        },
    )


__all__ = [
    "EmbeddingConfig",
    "get_embedding_config",
    "invalidate_embedding_cache",
]
