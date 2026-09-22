# Tests V6.8 — MODEL CAPABILITY REGISTRY (§52).
import sys
import warnings
from pathlib import Path

sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


from app.schemas.model_capabilities import (  # noqa: E402
    ModelCapabilities,
    get_model_capabilities,
    list_configured_models,
    supports,
)
from app.config import MODEL_NAME  # noqa: E402

# YAML de test avec fenêtre CONNUE + 2 modèles (cross-model §14)
TEST_YAML = Path("_test_models.yaml")
TEST_YAML.write_text(
    """
models:
  default:
    provider: ollama
    model: test-default
    context_window: null
    reserved_output_tokens: 2048
    max_output_tokens: null
    supports_tools: true
    supports_structured_output: false
    supports_vision: false
    supports_audio: false
  big-model:
    provider: ollama
    model: big-model
    context_window: 32000
    reserved_output_tokens: 2048
    max_output_tokens: 8192
    supports_tools: true
    supports_structured_output: true
    supports_vision: false
    supports_audio: false
""",
    encoding="utf-8",
)

print("--- §52 : Model Capability Registry ---")

# 1. Modèle avec fenêtre connue (big-model du YAML test)
caps = get_model_capabilities("big-model", path=TEST_YAML)
check(
    "1. fenêtre connue (big-model → 32000)",
    caps.context_window == 32000
    and caps.max_output_tokens == 8192,
    f"window={caps.context_window}",
)

# 2. Fenêtre inconnue (default → null)
caps = get_model_capabilities("default", path=TEST_YAML)
check(
    "2. fenêtre inconnue (default → None, pas inventée)",
    caps.context_window is None,
    str(caps.context_window),
)

# 12. structured output capability
check(
    "12. supports_structured_output : default false, big true",
    not supports(caps, "structured_output")
    and supports(
        get_model_capabilities("big-model", path=TEST_YAML),
        "structured_output",
    ),
)

# 13. tool calling capability
check(
    "13. supports_tools : default true (réel)",
    supports(caps, "tools")
    and not supports(caps, "vision")
    and not supports(caps, "audio"),
)

# 14. Cross-model config : nom inconnu → default cloné, capacités default
caps_unknown = get_model_capabilities(
    "modele-inconnu", path=TEST_YAML
)
check(
    "14a. nom inconnu → capacités default (rien inventé)",
    caps_unknown.context_window is None
    and caps_unknown.supports_tools is True
    and caps_unknown.supports_structured_output is False
    and caps_unknown.model_name == "modele-inconnu",
    f"{caps_unknown.model_name} window={caps_unknown.context_window}",
)

# 14b. Listing des modèles CONFIGURÉS (models.yaml, §38) : noms
# réels Ollama exposés (jamais la clé logique "default").
configured = list_configured_models(path=TEST_YAML)
check(
    "14b. list_configured_models : noms réels + providers",
    any(
        c["id"] == "test-default" and c["provider"] == "ollama"
        for c in configured
    )
    and any(
        c["id"] == "big-model" and c["provider"] == "ollama"
        for c in configured
    )
    and not any(
        c["id"] == "default" for c in configured
    ),
    str(configured),
)

# 14c. YAML absent → liste vide (repli décidé par l'appelant)
check(
    "14c. list_configured_models YAML absent → []",
    list_configured_models(path=Path("_inexistant.yaml")) == [],
    str(list_configured_models(Path("_inexistant.yaml"))),
)

# Registre réel du projet
caps_real = get_model_capabilities()
check(
    "15. registry réel : provider ollama, capacités honnêtes",
    caps_real.provider == "ollama"
    and caps_real.model_name == MODEL_NAME
    and isinstance(caps_real.supports_tools, bool)
    and caps_real.supports_vision is False,
    f"{caps_real.provider}/{caps_real.model_name}",
)

# YAML absent → defaults sûrs (pas de crash)
caps_no_yaml = get_model_capabilities(
    "x", path=Path("_inexistant.yaml")
)
check(
    "16. YAML absent → defaults sûrs sans crash",
    caps_no_yaml.context_window is None
    and caps_no_yaml.reserved_output_tokens == 2048,
)

# Schéma : champs null autorisés (capacité inconnue ≠ inventée)
check(
    "17. ModelCapabilities accepte null (inconnu ≠ inventé)",
    ModelCapabilities().context_window is None
    and ModelCapabilities().supports_tools is False,
)

TEST_YAML.unlink(missing_ok=True)

# Résumé
print()
fails = [label for label, ok in results if not ok]
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} "
    f"| FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("TESTS V6.8 MODELS: OK")
