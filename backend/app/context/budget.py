# Context Budget V6.8 (§40-§48).
#
# Gestion du budget de contexte : estimation, priorités des
# sources, compression — préparation multi-modèles à fenêtres
# différentes SANS nouveau provider (§36).
#
# §40 : si la fenêtre est inconnue (null), on n'invente PAS de
# valeur arbitraire — on applique un fallback CONSERVATEUR
# documenté (CONSERVATIVE_ASSUMED_WINDOW) et le statut porte
# "unknown" pour signaler l'assomption.
#
# §41 priorités (P0 jamais supprimé §43) :
#   P0 : system/core, message utilisateur courant, activité
#   P1 : contexte subject/topic + learning profile
#   P2 : knowledge + search results
#   P3 : user memory
#   P4 : thread / ancien contexte
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.context.model_capabilities import (
    ModelCapabilities,
    get_model_capabilities,
)

# Fenêtre ASSUMÉE quand context_window est null (§40).
# 8192 = plancher prudent des LLMs modernes : mieux vaut
# sous-estimer que de dépasser silencieusement une fenêtre
# inconnue. Documenté + testé ; remplacé par la vraie valeur
# dès qu'elle est configurée dans models.yaml.
CONSERVATIVE_ASSUMED_WINDOW = 8192

BudgetStatus = Literal[
    "ok", "near_limit", "compressed", "exceeded", "unknown"
]

# Seuil (> 85% de l'available → near_limit, §48)
NEAR_LIMIT_RATIO = 0.85


class ContextBudget(BaseModel):
    """Budget de contexte d'un run (§40)."""

    context_window: int | None
    reserved_output_tokens: int
    available_input_tokens: int | None


class BudgetSection(BaseModel):
    """Section candidate du prompt avec sa priorité §41."""

    key: str
    priority: int = Field(ge=0, le=4)
    tokens: int = 0
    payload: Any = None


class BudgetResult(BaseModel):
    """Résultat de l'application du budget (§47)."""

    kept: list[BudgetSection] = Field(default_factory=list)
    dropped_keys: list[str] = Field(default_factory=list)
    estimated_input_tokens: int = 0
    budget_status: BudgetStatus = "unknown"
    sources_used: int = 0
    sources_dropped: int = 0


def estimate_tokens(text: str) -> int:
    """Estimation de tokens (§42) — implémentation initiale
    DOCUMENTÉE : ≈4 caractères par token (heuristique latine,
    raisonnable pour du texte FR/EN).

    Interface stable : un tokenizer exact par modèle pourra se
    brancher plus tard sans changer les appelants (§42).
    """
    if not text:
        return 0
    return max(1, ceil(len(text) / 4))


def build_budget(
    caps: ModelCapabilities | None = None,
) -> ContextBudget:
    """Budget depuis les capacités du modèle actif.

    window null → available null aussi : les calculs internes
    utilisent le fallback conservateur, mais le CONTRAT expose
    l'inconnu (jamais une valeur inventée présentée comme réelle).
    """
    if caps is None:
        caps = get_model_capabilities()
    window = caps.context_window
    available = (
        window - caps.reserved_output_tokens
        if window is not None
        else None
    )
    return ContextBudget(
        context_window=window,
        reserved_output_tokens=caps.reserved_output_tokens,
        available_input_tokens=available,
    )


def _effective_available(budget: ContextBudget) -> tuple[int, bool]:
    """(available_effectif, est_assumé) — §40 fallback conservateur."""
    if budget.available_input_tokens is not None:
        return budget.available_input_tokens, False
    return (
        CONSERVATIVE_ASSUMED_WINDOW
        - budget.reserved_output_tokens,
        True,
    )


def apply_budget(
    sections: list[BudgetSection],
    window: int | None,
    reserved: int,
) -> BudgetResult:
    """Applique le budget aux sections (§43-§48).

    Algorithme :
      1. total ≤ available            → ok (near_limit ≥ 85%)
      2. sinon compression DANS L'ORDRE :
         a. drop P4 (thread/ancien) — sections entières
         b. tronquer P3 (mémoire peu pertinente = dernières)
         c. réduire P2 search (top_k réduit, ordre préservé §44)
         d. tronquer P2 knowledge
      3. P0/P1 (system/message/activité/subject/learning)
         JAMAIS touchés (§43/§46)
      4. Statut : ok / near_limit / compressed / exceeded ;
         window null → unknown (assomption) sauf si compression
         nécessaire (compressed prime : action réelle).

    Jamais de crash : exceeded → on continue avec ce qui tient
    (les P0 restent, c'est le contrat §48).
    """
    budget = ContextBudget(
        context_window=window,
        reserved_output_tokens=reserved,
        available_input_tokens=(
            window - reserved if window is not None else None
        ),
    )
    available, assumed = _effective_available(budget)

    kept = [s for s in sections if s.priority >= 0]
    total = sum(s.tokens for s in kept)
    dropped: list[str] = []

    if total <= available:
        status: BudgetStatus = (
            "unknown" if assumed else "ok"
        )
        if not assumed and available > 0 and total >= NEAR_LIMIT_RATIO * available:
            status = "near_limit"
        return BudgetResult(
            kept=kept,
            dropped_keys=[],
            estimated_input_tokens=total,
            budget_status=status,
            sources_used=len(kept),
            sources_dropped=0,
        )

    # --- Compression §43 : P4 d'abord (sections entières) ---
    by_prio = sorted(kept, key=lambda s: -s.priority)  # P0/P1 en tête
    # On retire les plus basses priorités d'abord, sections entières
    p4 = [s for s in kept if s.priority == 4]
    for s in p4:
        if total <= available:
            break
        kept.remove(s)
        dropped.append(s.key)
        total -= s.tokens

    # --- P3 : tronquer la mémoire peu pertinente (dernières) ---
    if total > available:
        p3 = [s for s in kept if s.priority == 3]
        for s in reversed(p3):  # les moins pertinentes d'abord
            if total <= available:
                break
            if s in kept:
                kept.remove(s)
                dropped.append(s.key)
                total -= s.tokens

    # --- P2 : réduire search (top_k réduit §44) puis knowledge ---
    if total > available:
        for s in kept:
            if total <= available:
                break
            if s.priority == 2 and s.key == "web_search":
                # garder la MOITIÉ des résultats (les premiers :
                # ordre de pertinence déjà trié par le ranking)
                results = s.payload or []
                if isinstance(results, list) and len(results) > 1:
                    half = results[: max(1, len(results) // 2)]
                    new_tokens = sum(
                        estimate_tokens(
                            str(r.get("content", ""))
                            + str(r.get("snippet", ""))
                        )
                        for r in half
                        if isinstance(r, dict)
                    ) or s.tokens // 2
                    total -= s.tokens - new_tokens
                    s.tokens = new_tokens
                    s.payload = half

    if total > available:
        # Toujours au-delà : exceeded — on continue quand même
        # avec ce qui reste (P0 intacts). Jamais de crash §48.
        status = "exceeded"
    else:
        status = "compressed"

    if assumed and status == "ok":
        status = "unknown"

    return BudgetResult(
        kept=kept,
        dropped_keys=dropped,
        estimated_input_tokens=total,
        budget_status=status,
        sources_used=len(kept),
        sources_dropped=len(dropped),
    )


__all__ = [
    "ContextBudget",
    "BudgetSection",
    "BudgetResult",
    "BudgetStatus",
    "CONSERVATIVE_ASSUMED_WINDOW",
    "estimate_tokens",
    "build_budget",
    "apply_budget",
]
