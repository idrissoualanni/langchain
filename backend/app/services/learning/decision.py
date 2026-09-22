# Learning Decision V7 — contrat de décision pédagogique (§5-§7).
#
# FRONTIÈRE FONDAMENTALE (§32 du brief V7) :
#   LearningContextInfo = FAITS de progression (ce qui est observé)
#   LearningDecision    = CHOIX pédagogique (ce qu'il faut faire)
#   AgentResponse       = représentation frontend (ce qui est affiché)
# Ces trois contrats ne sont JAMAIS fusionnés (extra=forbid V6.8.1).
#
# Le moteur (engine.py) PRODUIT une LearningDecision. Il ne
# l'EXÉCUTE pas : l'orchestration (dynamic_prompt / LLM / tools)
# consomme la décision — recommended_tool est une RECOMMANDATION
# (§24-§25), jamais un appel direct.
from typing import Any, Literal

from pydantic import BaseModel, Field

# Les 12 actions pédagogiques (§6/§7) — chacune a une définition
# précise dans le docstring de la classe.
LearningAction = Literal[
    "answer",            # réponse directe, pas de stratégie supersposée
    "explain",           # explication ciblée d'un concept
    "practice",          # créer une activité pratique (create_exercise)
    "hint",              # indice sur une activité EXISTANTE
    "evaluate",          # évaluer une réponse existante
    "quiz",              # lancer un quiz (create_quiz)
    "review",            # réviser un topic insuffisamment maîtrisé
    "deepen",            # approfondir un topic maîtrisé
    "advance_topic",     # passer à un nouveau topic pertinent
    "clarify",           # demander une précision avant de choisir
    "continue_activity", # poursuivre l'activité courante
    "complete_activity", # terminer proprement l'activité courante
]

# Transitions autorisées depuis les statuts d'activité V5.2 (§34).
# L'activité COURANTE prime (§8/§33) : depuis un statut actif, le
# moteur ne peut choisir QUE parmi les actions compatibles — jamais
# de nouveau topic au milieu d'un exercice.
ACTIVITY_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "idle": (
        # pas d'activité → toute stratégie neuve possible
        "explain", "practice", "quiz", "review", "deepen",
        "advance_topic", "clarify", "answer",
    ),
    "waiting_for_answer": (
        # l'étudiant doit répondre → évaluer / poursuivre / aider
        "evaluate", "continue_activity", "hint",
        "complete_activity",
    ),
    "waiting_for_retry": (
        "evaluate", "continue_activity", "hint",
        "complete_activity",
    ),
    "evaluating": (
        # boucle d'évaluation en cours → la terminer
        "continue_activity", "complete_activity",
        "review", "deepen",
    ),
    "giving_hint": (
        # indice donné → attendre/évaluer la nouvelle tentative
        "evaluate", "continue_activity", "complete_activity",
    ),
    "checking_understanding": (
        # boucle de compréhension → la fermer
        "continue_activity", "complete_activity",
        "review", "deepen",
    ),
    "completed": (
        # activité finie → stratégie neuve possible (§33)
        "explain", "practice", "quiz", "review", "deepen",
        "advance_topic", "clarify", "answer",
    ),
    "abandoned": (
        "explain", "practice", "quiz", "review", "deepen",
        "advance_topic", "clarify", "answer",
    ),
}


class LearningDecision(BaseModel):
    """Décision pédagogique UNIQUE produite par le Learning Engine.

    Next Best Action (§23) : UNE action principale, un sujet, un
    topic, une raison lisible, une confiance, une priorité. Les
    alternatives éventuelles vivent dans metadata — jamais deux
    actions principales.

    Champs (§5) :
      action          : une des 12 actions §6/§7
      subject/topic   : CIBLE de la décision (routés, pas devinés)
      reason          : raison lisible FR (exposée au prompt V7 §31
                        et au Context Inspector §47 — jamais les
                        scores internes)
      confidence      : confiance de la décision [0..1]
      priority        : score de priorité agrégé §22 (ordre relatif
                        des règles, pas un seuil absolu)
      activity_id     : si l'action cible une activité existante
      recommended_tool: tool pédagogique suggéré (§24 — create_exercise,
                        evaluate_answer, give_hint, create_quiz,
                        assess_understanding, propose_review) ;
                        l'orchestration décide de l'appel réel
      metadata        : alternatives + trajectoire + détail de
                        scoring (documentation, jamais affiché brut
                        à l'étudiant)
    """

    model_config = {"extra": "forbid"}

    action: LearningAction = Field(
        description="Action pédagogique choisie (§6/§7)"
    )
    subject: str | None = Field(
        default=None,
        description="Matière ciblée (routée, jamais devinée)",
    )
    topic: str | None = Field(
        default=None,
        description="Topic ciblé (routé, jamais deviné)",
    )
    reason: str = Field(
        description="Raison lisible de la décision (FR)"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiance de la décision [0..1]",
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Priorité agrégée (§22) — ordre relatif",
    )
    activity_id: str | None = Field(
        default=None,
        description="Activité ciblée si existante (§33)",
    )
    recommended_tool: str | None = Field(
        default=None,
        description="Tool suggéré (§24) — l'orchestration décide",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Alternatives, trajectoire, détail scoring",
    )


__all__ = [
    "LearningDecision",
    "LearningAction",
    "ACTIVITY_TRANSITIONS",
]
