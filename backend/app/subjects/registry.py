# Subject Registry — matières chargées depuis Neon ( subject_definitions ).
#
# Mission « aucune base de connaissance codée en dur » : les YAML de
# définition ne vivent plus dans le dépôt — ils sont stockés dans Neon
# ( seedés par scripts/migrate_knowledge_neon.py, éditables ensuite ).
# Ordre de chargement :
#   1. Neon subject_definitions ( source de vérité ) ;
#   2. repli : definitions/*.yaml local UNIQUEMENT s'il existe
#      ( bootstrap avant seed, tests ) — après migration le dossier
#      n'existe plus, le repli est un no-op.
import threading
from pathlib import Path

import yaml

from app.logging.events import log_event
from app.schemas.subject import SubjectConfig

# Dossier local historique — conservé pour le repli bootstrap/tests.
DEFINITIONS_DIR = Path(__file__).parent / "definitions"

_registry: dict[str, SubjectConfig] | None = None
_lock = threading.RLock()


def _load_from_neon() -> dict[str, SubjectConfig] | None:
    """YAML de matières depuis Neon. None si base injoignable/vide
    ( le caller passe alors au repli local )."""
    try:
        from app.services.knowledge import store as knowledge_store

        # only_validated=True : GATING fail-closed — une matière dont
        # status <> 'validated' n'est JAMAIS servie à l'agent ( ni
        # routing, ni tools, ni corpus ). L'admin passe par
        # load_subject_meta() / only_validated=False pour tout voir.
        raw = knowledge_store.load_subject_definitions(only_validated=True)
    except Exception as exc:  # noqa: BLE001
        log_event(
            "SUBJECT_REGISTRY_NEON_ERROR",
            level="WARNING",
            message=f"subject_definitions injoignable: {exc}",
        )
        return None
    if not raw:
        return None
    registry: dict[str, SubjectConfig] = {}
    for subject_id, yaml_text in sorted(raw.items()):
        try:
            data = yaml.safe_load(yaml_text) or {}
            cfg = SubjectConfig.from_dict(data)
            registry[cfg.id] = cfg
        except Exception as exc:  # noqa: BLE001
            log_event(
                "SUBJECT_REGISTRY_ERROR",
                level="ERROR",
                message=f"YAML Neon invalide pour {subject_id}: {exc}",
            )
    return registry


def _load_from_local() -> dict[str, SubjectConfig]:
    """Repli bootstrap : dossier definitions/ local ( absent après
    migration — glob vide → registry vide, sans erreur )."""
    registry: dict[str, SubjectConfig] = {}
    for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            cfg = SubjectConfig.from_dict(data)
            registry[cfg.id] = cfg
        except Exception as exc:  # noqa: BLE001
            log_event(
                "SUBJECT_REGISTRY_ERROR",
                level="ERROR",
                message=f"Failed to load {path.name}: {exc}",
            )
    return registry


def load_registry() -> dict[str, SubjectConfig]:
    """Charge les matières ( singleton thread-safe ) — Neon d'abord."""
    global _registry
    if _registry is not None:
        return _registry
    with _lock:
        if _registry is None:
            registry = _load_from_neon()
            source = "neon"
            if registry is None:
                registry = _load_from_local()
                source = "local"
            _registry = registry
            log_event(
                "SUBJECT_REGISTRY_LOADED",
                message=(
                    f"Registry loaded | source={source} | "
                    f"subjects={sorted(registry.keys())}"
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
