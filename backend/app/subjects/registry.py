# Subject Registry — matières chargées depuis definitions/*.yaml
# Ajouter une matière = 1 fichier YAML + knowledge. Zéro modification moteur.
import threading
from pathlib import Path

import yaml

from app.logging.events import log_event
from app.schemas.subject import SubjectConfig

DEFINITIONS_DIR = Path(__file__).parent / "definitions"

_registry: dict[str, SubjectConfig] | None = None
_lock = threading.RLock()


def load_registry() -> dict[str, SubjectConfig]:
    """Charge toutes les definitions/*.yaml (singleton thread-safe)."""
    global _registry
    if _registry is not None:
        return _registry
    with _lock:
        if _registry is None:
            registry: dict[str, SubjectConfig] = {}
            for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    cfg = SubjectConfig.from_dict(data)
                    registry[cfg.id] = cfg
                except Exception as exc:
                    log_event(
                        "SUBJECT_REGISTRY_ERROR",
                        level="ERROR",
                        message=f"Failed to load {path.name}: {exc}",
                    )
            _registry = registry
            log_event(
                "SUBJECT_REGISTRY_LOADED",
                message=(
                    f"Registry loaded | subjects={sorted(registry.keys())}"
                ),
            )
    return _registry


def get_subject(subject_id: str) -> SubjectConfig | None:
    """SubjectConfig par id, None si inconnu."""
    return load_registry().get(subject_id)


def list_subjects() -> list[SubjectConfig]:
    return sorted(load_registry().values(), key=lambda s: s.id)


def invalidate() -> None:
    """Recharge forcé (tests)."""
    global _registry
    with _lock:
        _registry = None
