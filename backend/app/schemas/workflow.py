# Subgraph Contracts — contrats d'entrée/sortie des subgraphs (§8).
#
# Chaque subgraph expose SANS exposer son état interne :
#
#   Input (SubgraphInput)
#   → workflow (nodes internes privés)
#   → Output (SubgraphResult — résultat structuré)
#
# Les détails internes restent privés (§5 : jamais exposer le state
# interne au Main Graph). Typage strict extra=forbid, cohérent avec
# les contrats pydantic existants (RoutingResult, BuiltContext, ...).
#
# Déplacé depuis app/graph/subgraphs/contracts.py (refactor : les
# contrats vivent dans app/schemas/). AJOUT refactor : DocumentResult
# (§14 mission — le workflow "document" avait un SubgraphResult
# générique ; il a désormais son contrat affiné).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkflowName = Literal[
    "main",
    "activity",
    "problem",
    "coding",
    "research",
    "video",
    "document",
]

# Notion V6.5 des statuts de recherche — réutilisée par plusieurs
# subgraphs (research, video) pour rester cohérent MAIS sans importer
# app.schemas.context ici (les contrats subgraph ne dépendent pas de
# la couche contexte ; les valeurs concordent avec SearchResponse).
JobStatus = Literal[
    "ok",
    "error",
    "partial",
    "cancelled",
    "pending",
]


class SubgraphInput(BaseModel):
    """Entrée standardisée d'un subgraph (§8).

    Un subgraph reçoit TOUJOURS ce contrat minimal — jamais le
    MainState complet (frontière nette, §5/§8). Les champs
    workflow-spécifiques arrivent dans "payload".

    user_id/thread_id  : identité — isolation stricte des données
                         (le subgraph n'ajoute jamais de scope)
    query              : demande normalisée (ex : énoncé de problème,
                         prompt de code, sujet de recherche)
    payload            : dict libre workflow-spécifique (validé par
                         le subgraph lui-même) — vide par défaut
    """

    model_config = {"extra": "forbid"}

    user_id: str = Field(default="")
    thread_id: str = Field(default="")
    query: str = Field(default="")
    payload: dict = Field(default_factory=dict)


class SubgraphResult(BaseModel):
    """Résultat structuré produit par un subgraph (§8).

    Contrat de SORTIE commun à tous les subgraphs :
      workflow : nom du workflow qui a produit ce résultat
      status   : JobStatus (ok / error / partial / cancelled /
                 pending)
      message  : message lisible (raison / erreur / résumé court)

    Chaque subgraph définit SES champs dérivés via une sous-classe
    (ProblemResult, CodingResult, ...). Le Main Graph consomme le
    SubgraphResult (workflow + status), jamais les détails internes.
    """

    model_config = {"extra": "forbid"}

    workflow: WorkflowName = Field(
        description="Nom du workflow producteur"
    )
    status: JobStatus = Field(
        default="ok",
        description="Statut du travail (ok/error/partial/cancelled/"
        "pending)",
    )
    message: str = Field(
        default="",
        description="Message lisible (raison/erreur/résumé)",
    )


class ProblemResult(SubgraphResult):
    """Sortie du ProblemSubgraph (§21/§8).

    Résultat de la résolution DÉTERMINISTE d'un énoncé : parsing
    structuré, plan attendu, validation. Les détails internes
    (ProblemState) ne sont jamais exposés — seule la synthèse.
    """

    understanding: dict = Field(
        default_factory=dict,
        description="Analyse de l'énoncé (concepts détectés, "
        "variables, inconnues)",
    )
    solution_steps: list[dict] = Field(
        default_factory=list,
        description="Étapes attendues DE COMPARAISON (déterministes, "
        "artefact)",  # plan interne
    )
    verdict: str = Field(
        default="",
        description="Verdict de validation (ex: correct, "
        "plan_incomplet, mal_formule)",
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confiance du verdict [0..1]",
    )
    markdown: str = Field(
        default="",
        description="Artefact Markdown de la résolution (§21)",
    )


class CodingResult(SubgraphResult):
    """Sortie du CodingSubgraph (§22-§25/§8).

    Synthèse de la boucle de code : tests, analyse statique,
    sécurité. Le code complet peut être signifié via code_summary.
    """

    tested: bool = Field(
        default=False,
        description="Une suite de tests a-t-elle tourné ?",
    )
    tests: dict = Field(
        default_factory=dict,
        description="{passed, failed, total} — résultats de tests",
    )
    analysis: dict = Field(
        default_factory=dict,
        description="Analyse statique (lint, erreurs détectées)",
    )
    security: dict = Field(
        default_factory=dict,
        description="Scan de sécurité (issues, verdict)",
    )
    code_summary: str = Field(
        default="",
        description="Résumé lisible du code produit/modifié",
    )


class ResearchResult(SubgraphResult):
    """Sortie du ResearchSubgraph (§26-§27/§8).

    Synthèse de la deep research : plan, claims sourcés.
    """

    plan: list[str] = Field(
        default_factory=list,
        description="Étapes de recherche suivies (planner)",
    )
    claims: list[dict] = Field(
        default_factory=list,
        description="Claims extraits [{claim, source, confidence}]",
    )
    summary: str = Field(
        default="",
        description="Synthèse consolidée sourcée",
    )


class VideoResult(SubgraphResult):
    """Sortie du VideoSubgraph (§28-§29/§8).

    Résultat de l'ingestion vidéo : transcription + segmentation
    pédagogique, prêt à ingérer en knowledge.
    """

    video_id: str = Field(
        default="",
        description="Identifiant de la vidéo ingérée",
    )
    transcript: str = Field(
        default="",
        description="Transcription en texte intégral",
    )
    visual_description: str = Field(
        default="",
        description="Description visuelle produite par l'agent ReAct "
        "(slides, diagrammes, écran de code…). Vide si l'agent vision "
        "est désactivé ou n'a rien trouvé d'exploitable.",
    )
    segments: list[dict] = Field(
        default_factory=list,
        description="Segments pédagogiques [{title, summary, "
        "start, end, topics}]",
    )
    knowledge_keys: list[str] = Field(
        default_factory=list,
        description="Clés knowledge créées (ingestion §30)",
    )


class ActivityResult(SubgraphResult):
    """Sortie de l'activité pédagogique (§14-§17/§8).

    L'ActivitySubgraph implémentera la continuation/évaluation
    d'une activité (Phase 2). Ce contrat fixe déjà sa sortie.
    """

    activity_id: str = Field(
        default="",
        description="Activité concernée",
    )
    activity_type: str = Field(
        default="",
        description="exercise | quiz | understanding_check",
    )
    evaluated: bool = Field(
        default=False,
        description="Une évaluation a-t-elle été produite ?",
    )
    evaluation: dict = Field(
        default_factory=dict,
        description="Résultat d'évaluation (score, verdict, "
        "feedback) — deterré en Phase 2 (Evaluation Engine §18-§20)",
    )


class DocumentResult(SubgraphResult):
    """Sortie du DocumentSubgraph (§30/§8) — AJOUT refactor §14.

    Remplace le SubgraphResult générique : l'ingestion documentaire
    (upload/chunk/index/persist) expose désormais son propre contrat
    affiné — le Main Graph continue de consommer workflow + status.
    """

    doc_id: str = Field(
        default="",
        description="Document concerné (vide si action globale)",
    )
    filename: str = Field(
        default="",
        description="Nom de fichier concerné",
    )
    action: str = Field(
        default="",
        description="Action traitée (upload/search/list/delete)",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Chunks indexés (ingestion) ou exploités",
    )


# Registry des CONTRATS — le Main Graph résout la sortie attendue
# d'un workflow sans connaître l'implémentation du subgraph (§8).
SUBGRAPH_RESULTS: dict[str, type[SubgraphResult]] = {
    "activity": ActivityResult,
    "problem": ProblemResult,
    "coding": CodingResult,
    "research": ResearchResult,
    "video": VideoResult,
    "document": DocumentResult,
}

# Workflows de l'application (source de vérité du WorkflowRouter).
KNOWN_WORKFLOWS: tuple[str, ...] = (
    "main",
    "activity",
    "problem",
    "coding",
    "research",
    "video",
    "document",
)

__all__ = [
    "WorkflowName",
    "JobStatus",
    "SubgraphInput",
    "SubgraphResult",
    "ProblemResult",
    "CodingResult",
    "ResearchResult",
    "VideoResult",
    "ActivityResult",
    "DocumentResult",
    "SUBGRAPH_RESULTS",
    "KNOWN_WORKFLOWS",
]
