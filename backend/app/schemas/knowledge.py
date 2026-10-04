# Knowledge Schemas — contrats de la base de connaissance ( corpus Neon ).
#
# Regroupe les types de l'ingestion / gouvernance / visualisation du
# corpus de cours. Les contrats de RETRIEVAL ( SearchResult… ) restent
# dans app/schemas/context.py ; ici on trouve :
#   - ChunkFrontmatter     : en-tête YAML d'une page Markdown d'import ;
#   - SectionUpsertRequest : écriture admin d'une section ( + author ) ;
#   - SubjectStatusUpdate  : cycle de validation admin d'une matière ;
#   - ChunkVector3D / ChunkVizResponse / ChunkEdge : visualisation 3D ;
#   - ReconcileResponse    : résultat de la réconciliation de sources.
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.subject import SubjectStatus


class ChunkFrontmatter(BaseModel):
    """En-tête YAML (`---…---`) d'une page Markdown source.

    Décrit l'appartenance d'une page au corpus : matière, topic,
    auteur et titre. Le statut n'est PAS piloté par le fichier — il
    est géré par l'admin ( cf. SubjectStatusUpdate ) ; le champ
    `status` du frontmatter reste indicatif.
    """

    model_config = ConfigDict(extra="allow")

    subject: str = Field(default="", max_length=64)
    topic: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)
    author: str = Field(default="", max_length=200)
    source: str = Field(default="", max_length=300)
    status: SubjectStatus = "draft"


class SectionUpsertRequest(BaseModel):
    """Création / remplacement d'une section de cours ( admin )."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source_label: str | None = Field(default=None, max_length=200)
    author: str = Field(default="", max_length=200)


class SubjectStatusUpdate(BaseModel):
    """Mise à jour du statut de validation ( et éventuellement auteur )."""

    model_config = ConfigDict(extra="forbid")

    status: SubjectStatus
    author: str | None = Field(default=None, max_length=200)


class ChunkVector3D(BaseModel):
    """Un chunk projeté en 3D pour la visualisation admin."""

    model_config = ConfigDict(extra="forbid")

    id: int
    x: float
    y: float
    z: float
    subject_id: str = ""
    topic_slug: str = ""
    title: str = ""
    author: str = ""
    source_label: str = ""


class ChunkEdge(BaseModel):
    """Arête kNN entre deux chunks ( voisinage sémantique ) — tracé Line."""

    model_config = ConfigDict(extra="forbid")

    source: int
    target: int
    distance: float


class ChunkVizResponse(BaseModel):
    """Réponse de la visualisation 3D des chunks vectorisés.

    `explained_variance` = part de variance portée par chaque axe PCA
    ( pour légender le graphique ) ; `dim` = dimension d'origine des
    embeddings ; `projection` = "pca3d".
    """

    model_config = ConfigDict(extra="forbid")

    projection: str = "pca3d"
    points: list[ChunkVector3D] = Field(default_factory=list)
    edges: list[ChunkEdge] = Field(default_factory=list)
    count: int = 0
    dim: int = 0
    explained_variance: list[float] = Field(default_factory=list)
    subject_id: str | None = None


class ReconcileResponse(BaseModel):
    """Résultat de la réconciliation ( suppression des sources disparues )."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str
    live_sources: int = 0
    deleted_sections: int = 0
    deleted_files: int = 0


class KnowledgeProposal(BaseModel):
    """Une proposition de connaissance soumise par l'agent ( vue admin ).

    `pending` tant qu'un admin n'a pas tranché ; `approved` → la section
    est vectorisée et entre dans le corpus ; `rejected` → écartée.
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    subject_id: str
    title: str
    content: str = ""
    author: str = ""
    proposed_by: str = ""
    reason: str = ""
    status: str = "pending"
    created_at: str = ""
    decided_at: str = ""
    decided_by: str = ""


class ProposalDecision(BaseModel):
    """Décision admin sur une proposition ( approuver / rejeter )."""

    model_config = ConfigDict(extra="forbid")

    approve: bool


__all__ = [
    "ChunkFrontmatter",
    "SectionUpsertRequest",
    "SubjectStatusUpdate",
    "ChunkVector3D",
    "ChunkEdge",
    "ChunkVizResponse",
    "ReconcileResponse",
    "KnowledgeProposal",
    "ProposalDecision",
]
