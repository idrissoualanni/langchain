# Context Schemas V5 — schémas structurés CENTRALISÉS (§11/§14/§30).
#
# Séparation LangChain native vs business logic :
#   - Runtime Context  = DONNÉES D'EXÉCUTION (user_id, thread_id) —
#     transporté par le mécanisme officiel context= de create_agent,
#     PAS injecté dans le prompt ni passé via configurable.
#   - RoutingResult    = sortie VALIDÉE du router (pydantic, §14)
#   - KnowledgeResult  = item knowledge structuré (§24)
#   - BuiltContext     = contexte métier assemblé par le Context
#     Builder (§30) — sélectionné puis présenté par le Prompt Builder.
from dataclasses import dataclass, field
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

# V6.8.1 §20 : le contrat learning vit dans app.learning.schemas
# (LearningContextInfo). Import direct SANS cycle : app.learning
# ne dépend pas d'app.context (audit V6.8.1 §4). Idem budget /
# model_capabilities : ils n'importent pas app.context.schemas
# en retour — résolution runtime des annotations Pydantic.
from app.context.budget import ContextBudget
from app.context.model_capabilities import ModelCapabilities
from app.learning.schemas import LearningContextInfo


# ------------------------------------------------------------------
# Runtime Context (§4/§5) — user_id/thread_id en DI native LangChain
# ------------------------------------------------------------------


@dataclass
class AgentContext:
    """Contexte d'exécution transporté par LangGraph Runtime.

    Transmis via agent.invoke(..., context=AgentContext(...)) —
    accessible dans middleware/tools via request.runtime.context /
    runtime.context. Jamais injecté tel quel dans le prompt (§36).

    user_id   : identité persistante — isole le Store mémoire
    thread_id : conversation courante (redondant avec le
                configurable du checkpointer, mais disponible pour
                les outils/middleware sans get_config()).
    """

    user_id: str = ""
    thread_id: str = ""


# ------------------------------------------------------------------
# Routing (§14) — sortie structurée validée du router
# ------------------------------------------------------------------


class RoutingResult(BaseModel):
    """Résultat de classification d'une question par le router.

    Le router répond UNIQUEMENT à « de quoi parle la demande ? »
    (§15) — jamais quelle réponse donner.

    V6.8.1 §26 : extra=forbid — RoutingResult est un contrat
    de ROUTING SEUL : RoutingResult(learning=..., knowledge=...)
    est REJETÉ (incompatibilité explicite, jamais silencieuse).
    """

    model_config = {"extra": "forbid"}

    model_config = {"extra": "forbid"}

    status: Literal[
        "supported",
        "ambiguous",
        "unsupported",
        "unknown",
        "multi_domain",
    ] = Field(
        default="unknown",
        description="Statut du routing : supported (matière "
        "configurée), ambiguous (plusieurs interprétations), "
        "unsupported (matière détectée non configurée), unknown "
        "(rien d'identifié), multi_domain (domaines multiples)",
    )
    subject: str | None = Field(
        default=None,
        description="id de la matière si détectée (ex: python)",
    )
    topic: str | None = Field(
        default=None,
        description="topic si identifiable (ex: return)",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confiance du routing [0..1]",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="Matières candidates si ambiguous",
    )
    subjects: list[str] = Field(
        default_factory=list,
        description="Matières des domaines si multi_domain",
    )
    # --- V7.1 (mission §9/§13/§14) : extension COMPATIBLE ---
    # match_type : quelle couche a porté la décision (Literal
    # Pydantic §9). Default "lexical" = comportement V6.5 pur.
    match_type: Literal[
        "exact",
        "lexical",
        "morphological",
        "semantic",
        "hybrid",
    ] = Field(
        default="lexical",
        description="Type de match V7.1 : exact (alias/topic "
        "plein), lexical (tokens), morphological (variantes "
        "singulier/pluriel), semantic (embedding seul), hybrid "
        "(lexical+semantic)",
    )
    # semantic_status : état de la couche sémantique pour CE
    # routing (§19). Default "unavailable" = honnête : aucune
    # tentative sémantique n'a été faite (cas lexical V6.5 pur,
    # hint explicite, tests V5/V6 non modifiés).
    semantic_status: Literal[
        "available",
        "unavailable",
        "error",
    ] = Field(
        default="unavailable",
        description="État de la couche sémantique V7.1 : "
        "available (candidates scorées), unavailable (pas de "
        "tententative/provider absent), error (exception → "
        "lexical fallback)",
    )
    # topic_candidates : candidats HYBRIDES avec scores (§11 —
    # jamais « premier du YAML »). list[dict] pour rester
    # sérialisable directement ; vide = pas de ranking hybride
    # (comportement V6.5 pur).
    topic_candidates: list[dict] = Field(
        default_factory=list,
        description="Candidats hybrides [{subject, topic, score, "
        "lexical_score, semantic_score, match_type}] triés par "
        "score décroissant (§11) — Inspector/dev uniquement",
    )


# ------------------------------------------------------------------
# Fallback (V6.6 §5) — décision structurée entre routing/search
# ------------------------------------------------------------------


class FallbackDecision(BaseModel):
    """Décision de fallback V6.6 (§5/§6).

    COUCHE DE DÉCISION — ne duplique NI RoutingResult NI
    SearchResponse : elle consomme leurs statuts et produit
    UNE action explicite + une raison lisible.

    Actions (§6) :
      use_local_knowledge      → le contexte de cours suffit
      use_web_search           → les résultats web sont la source
      ask_clarification        → ambigu/multi-domain/vague
      use_general_tutor        → rien de fiable disponible
      continue_without_external_search → défense (statut inattendu)

    source_status : concaténation documentée des états d'origine
    (ex: "supported/insufficient/web_error") — les états ne sont
    JAMAIS convertis silencieusement (§7).

    V6.8.1 §26 : extra=forbid — contrat de DÉCISION, il ne
    transporte ni routing ni results (incompatibilité rejetée).
    """

    model_config = {"extra": "forbid"}

    action: Literal[
        "use_local_knowledge",
        "use_web_search",
        "ask_clarification",
        "use_general_tutor",
        "continue_without_external_search",
    ] = Field(
        description="Action de fallback décidée (matrice §6)"
    )
    reason: str = Field(
        description="Raison lisible de la décision (§8 : "
        "transparente dans le prompt LLM)"
    )
    source_status: str = Field(
        default="",
        description="États d'origine concaténés "
        "(routing/knowledge/web) — jamais réduits à « not found »",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confiance de la décision [0..1]",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="Matières candidates si clarification",
    )


# ------------------------------------------------------------------
# Knowledge (§24) — item de connaissance structuré
# ------------------------------------------------------------------


class SearchResult(BaseModel):
    """Résultat de recherche UNIFIÉ V6.5 (§3 Search Contract).

    Toute source (knowledge local, web) produit ce format — le
    Context Builder ne consomme QUE ça. Jamais de chaîne
    concaténée brute.

    V6.8.1 §26 : extra=forbid — item retrieval strict (le
    topic knowledge est une EXTENSION KnowledgeResult, pas un
    champ ad hoc ici).
    """

    model_config = {"extra": "forbid"}

    title: str = Field(
        default="",
        description="Titre lisible (ex: « Python — Fonctions »)",
    )
    source: str = Field(
        description="Chemin/origine (ex: python/functions, "
        "docs.python.org)",
    )
    url: str | None = Field(
        default=None,
        description="URL si source web, None si knowledge local",
    )
    content: str = Field(
        description="Contenu exploitable de la source",
    )
    snippet: str | None = Field(
        default=None,
        description="Extrait court (web) — None si non pertinent",
    )
    relevance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de pertinence [0..1] (formule §42-C)",
    )
    source_type: Literal[
        "local_knowledge",
        "web",
        "user_document",
        "other",
    ] = Field(
        default="local_knowledge",
        description="Type de source — JAMAIS inventé (§26)",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Métadonnées internes (topic, section...)",
    )


class SearchResponse(BaseModel):
    """Réponse de recherche unifiée V6.5 (§3).

    status :
      found        → ≥1 résultat ≥ seuil
      insufficient → sources parcourues, rien de pertinent
      unavailable  → source indisponible (pas de config / pas
                     de clé / service absent)
      error        → échec technique (exception, réseau)
    """

    model_config = {"extra": "forbid"}

    status: Literal[
        "found",
        "insufficient",
        "unavailable",
        "error",
    ] = Field(default="unavailable")
    query: str = Field(
        default="",
        description="Requête NORMALISÉE réellement cherchée",
    )
    results: list[SearchResult] = Field(default_factory=list)


class KnowledgeResult(SearchResult):
    """Une section knowledge pertinente récupérée pour le run.

    Hérite SearchResult (source_type=local_knowledge) + garde
    topic en champ dédié pour le pont Registry↔knowledge.
    """

    topic: str = Field(
        default="",
        description="Topic de la section (ex: return) — champ "
        "pratique redondant avec metadata['section']",
    )

    @classmethod
    def from_search(
        cls, r: SearchResult, topic: str
    ) -> "KnowledgeResult":
        """Conversion SearchResult → KnowledgeResult."""
        return cls(
            title=r.title,
            source=r.source,
            url=r.url,
            content=r.content,
            snippet=r.snippet,
            relevance=r.relevance,
            source_type=r.source_type,
            metadata=r.metadata,
            topic=topic,
        )


class KnowledgeSearchResult(SearchResponse):
    """Recherche knowledge locale — VUE du contrat retrieval.

    V6.8.1 §8/§9 : SOUS-CLASSE de SearchResponse (plus deux
    systèmes parallèles). Le knowledge local utilise le même
    contrat retrieval (source_type=local_knowledge) ; cette vue
    ajoute :
      - items : vue historique V5 de results (les DEUX champs
        sont synchronisés par validateur — les consommateurs
        V5/V6 (prompt_builder, preview, tests) continuent de
        lire .items sans rupture ; migration progressive vers
        .results documentée)
      - searched_sources : volumétrie propre au knowledge local

    Compat : status "error" local est replié en "insufficient"
    par le builder (l'erreur est loggée SEARCH_ERROR) — le
    statut 4-valeurs du contrat retrieval est accepté ici.
    """

    items: list[KnowledgeResult] = Field(default_factory=list)
    searched_sources: int = Field(
        default=0,
        description="Nombre de sources knowledge parcourues",
    )

    @model_validator(mode="after")
    def _sync_items_results(self) -> "KnowledgeSearchResult":
        """items ↔ results synchronisés : items = vue typée
        KnowledgeResult, results = source de vérité retrieval.
        Si l'un est fourni seul, l'autre est dérivé."""
        if self.items and not self.results:
            object.__setattr__(
                self, "results", list(self.items)
            )
        elif self.results and not self.items:
            object.__setattr__(
                self,
                "items",
                [
                    r if isinstance(r, KnowledgeResult)
                    else KnowledgeResult.from_search(r, "")
                    for r in self.results
                ],
            )
        return self


# ------------------------------------------------------------------
# Tools (§28/§39) — résolution des tools disponibles
# ------------------------------------------------------------------


class ResolvedTools(BaseModel):
    """Tools réellement disponibles pour un run (resolve_tools).

    available     : tools IMPLÉMENTÉS fournis au modèle
    declared      : tools déclarés dans le SubjectConfig
    unavailable   : tools déclarés mais NON enregistrés (§39 :
                    loggés, jamais exposés au modèle)
    """

    model_config = {"extra": "forbid"}

    available: list[str] = Field(default_factory=list)
    declared: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)


# V6.8.1 : ContextPriority (Enum critical/high/medium/low) SUPPRIMÉ
# — contrat mort depuis V6.8 (le budget réel utilise P0-P4 dans
# budget.py, priorités §41). Aucun consommateur (audit §4).


# ------------------------------------------------------------------
# BuiltContext (§30) — le contexte métier assemblé
# ------------------------------------------------------------------


class SubjectContextInfo(BaseModel):
    """Config matière exposée au contexte (depuis le Registry)."""

    model_config = {"extra": "forbid"}

    id: str
    name: str
    domain: str
    description: str = ""
    teaching_style: list[str] = Field(default_factory=list)
    pedagogical_guidelines: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class UserContextInfo(BaseModel):
    """Contexte utilisateur sélectionné (mémoire + profil)."""

    model_config = {"extra": "forbid"}

    text: str = ""
    facts_count: int = 0


class ThreadContextInfo(BaseModel):
    """Contexte thread léger (métadonnées — PAS l'historique, §32)."""

    model_config = {"extra": "forbid"}

    thread_id: str = ""
    message_count: int | None = None
    text: str = ""


class ContextStats(BaseModel):
    """Budget contexte (§41/§47) — volumétrie + budget V6.8.

    Champs V6.8 avec defaults : aucun test/existant cassé.
    budget_status ∈ ok/near_limit/compressed/exceeded/unknown
    (§48) — unknown = fenêtre inconnue (assomption conservatrice
    documentée, budget.py).

    V6.8.1 §15 : TÉLÉMÉTRIE (résumé post-run exposé au
    preview/frontend). NE DUPlique PAS ContextBudget : le détail
    du budget (sections, drops) vit dans BuiltContext.budget.
    """

    model_config = {"extra": "forbid"}

    memories_used: int = 0
    knowledge_items: int = 0
    user_context_chars: int = 0
    context_size: int = 0
    # --- V6.8 §47 ---
    estimated_input_tokens: int = 0
    context_window: int | None = None
    reserved_output_tokens: int = 0
    available_input_tokens: int | None = None
    budget_status: str = "unknown"
    sources_used: int = 0
    sources_dropped: int = 0
    # --- V10 : documents personnels (RAG) ---
    user_documents_count: int = 0


class ActivityContextInfo(BaseModel):
    """Résumé de l'ACTIVITÉ pédagogique EN COURS (V6.8.1 §13/§16).

    VUE thread-locale de LearningActivityState (state LangGraph,
    activity_state.py) — construite par le builder quand une
    activité est active, POUR LE RUN courant uniquement.

    Frontières (§5-G/§13) :
      - ≠ LearningContextInfo : progression PERSISTANTE du
        profil (mastery...) — l'activité est l'ICI ET MAINTENANT
      - ≠ LearningActivityState : le TypedDict complet vit dans
        le state (source de vérité thread) ; ceci n'expose au
        contexte que les champs consommables (pas question/
        expected answer — les données de l'exercice ne sont
        JAMAIS mises dans le prompt).
    """

    model_config = {"extra": "forbid"}

    activity_id: str = ""
    activity_type: str = ""
    status: str = ""
    subject: str = ""
    topic: str = ""
    hint_level: int = 0
    attempts: int = 0


class DocumentContextInfo(BaseModel):
    """Documents PERSONNELS de l'utilisateur (RAG V10) injectés
    dans le contexte quand pertinents pour la question.

    VUE du retrieval documents (DocumentRetriever.inject_documents_context) :
      - text : bloc formaté « citations » déjà prêt pour le prompt
        (§34 — préambule + titre + extrait + URL local)
      - count : nombre de résultats gardés (0 = rien d'exploité)
      - status : found / insufficient / unavailable / error (cf.
        SearchResponse V6.5 §3 — statut UNIQUEMENT, jamais inventé)
      - searched_documents : documents parcourus (isolation user_id
        via RagStore — jamais d'accès cross-user, §15)

    Frontières (§5-?) : ≠ knowledge (cours Registry), ≠ web
    (fallback externe) — c'est la base documentaire PERSONNELLE.
    La section reste OPTIONNELLE : absente/insuffisante = le tuteur
    garde la conduite normale, sans jamais signaler d'erreur (§37).
    """

    model_config = {"extra": "forbid"}

    text: str = Field(
        default="",
        description="Bloc formaté prêt pour le prompt — vide si rien",
    )
    count: int = Field(
        default=0,
        ge=0,
        description="Nombre de résultats de documents gardés",
    )
    status: Literal[
        "found",
        "insufficient",
        "unavailable",
        "error",
    ] = Field(
        default="unavailable",
        description="Statut du retrieval documents (§3 SearchResponse)",
    )
    searched_documents: int = Field(
        default=0,
        ge=0,
        description="Documents utilisateur parcourus (source) ",
    )


class BuiltContext(BaseModel):
    """Contexte métier complet assemblé par le Context Builder.

    C'est l'objet structuré unique transmis au Prompt Builder —
    plus de dictionnaire non documenté (§11).

    V6.8.1 — CONTRAT AGRÉGÉ CANONIQUE (§16) :
      - chaque champ a UN propriétaire unique (classification
        §5 A-K) : routing=A, subject=K, knowledge/web=B,
        fallback=D, tools=K, user/thread=E, learning=F,
        activity=G, model=H, budget=I, stats=télémétrie
      - learning : TYPÉ LearningContextInfo (§20 — plus de dict
        anonyme) ; la vue dict (model_dump) reste disponible via
        .learning_dict pour la transition
      - budget : budget DÉTAILLÉ du run (§16/§15) — ContextStats
        reste le RÉSUMÉ télémétrie exposé
      - model : capacités du modèle actif (§14)
      - activity : résumé de l'activité thread-locale (§13)
      - §17 IMMUTABLE PAR CONVENTION : le Learning Engine V7
        (§23) fait decision = decide(built_context) SANS
        reconstruire — toute dérivation produit une COPIE
        (model_copy(update=...)), l'original n'est jamais muté
      - §26 extra=forbid : BuiltContext(unknown_source=...) est
        rejeté — pas de champ parallèle implicite
    """

    model_config = {"extra": "forbid"}

    routing: RoutingResult = Field(default_factory=RoutingResult)
    subject: SubjectContextInfo | None = None
    knowledge: KnowledgeSearchResult = Field(
        default_factory=KnowledgeSearchResult
    )
    web: "SearchResponse" = Field(
        default_factory=lambda: SearchResponse(
            status="unavailable"
        ),
        description="Recherche web V6.5 (§24) — remplie uniquement "
        "si knowledge insuffisant ET matière supportée. "
        "status=unavailable sinon (aucune tentative).",
    )
    fallback: "FallbackDecision" = Field(
        default_factory=lambda: FallbackDecision(
            action="continue_without_external_search",
            reason="default",
        ),
        description="Décision de fallback V6.6 (§6) — matrice "
        "routing/knowledge/web → action",
    )
    tools: ResolvedTools = Field(default_factory=ResolvedTools)
    user: UserContextInfo = Field(
        default_factory=UserContextInfo
    )
    thread: ThreadContextInfo = Field(
        default_factory=ThreadContextInfo
    )
    learning: LearningContextInfo | None = Field(
        default=None,
        description="Sélection Learning Profile PERTINENTE "
        "(V6.8.1 §20 : TYPÉE — progressivement consommée en "
        "attributs ; dict historique via .learning_dict)",
    )
    relevant_memories: list[dict] = Field(default_factory=list)
    stats: ContextStats = Field(default_factory=ContextStats)
    # --- V6.8.1 §16 : le budget détaillé et le modèle ont un
    # propriétaire dans l'agrégé (plus de champs hors contrat) ---
    budget: "ContextBudget | None" = Field(
        default=None,
        description="Budget détaillé du run (§15 : ContextBudget "
        "= état détaillé ; ContextStats = résumé télémétrie)",
    )
    model: "ModelCapabilities | None" = Field(
        default=None,
        description="Capacités du modèle actif (§14 — registry "
        "models.yaml)",
    )
    activity: ActivityContextInfo | None = Field(
        default=None,
        description="Résumé activité pédagogique thread-locale "
        "(§13 — nulle si aucune activité en cours)",
    )
    # --- V10 §2 : documents PERSONNELS de l'utilisateur (RAG) ---
    # Rempli par DocumentRetriever.inject_documents_context quand
    # des documents pertinents existent. Sémantiquement proche de
    # web (source externe à l'utilisateur) mais isolée : la base
    # documentaire est PROPRE à l'user_id (§15 isolation stricte).
    user_documents: DocumentContextInfo = Field(
        default_factory=DocumentContextInfo,
        description="Documents personnels pertinents (RAG V10) — "
        "status=unavailable si aucun document indexé, jamais "
        "d'exception propagée (§15 fail-safe)",
    )

    def learning_dict(self) -> dict | None:
        """Vue dict historique de learning (transition V6.8.1).

        Les consommateurs legacy (dict.get) migrent vers les
        attributs typés ; cette vue reste pour compat.
        """
        if self.learning is None:
            return None
        return self.learning.model_dump()


# Compatibilité d'import pour les modules qui référencent
# RouterResult (ancien nom dataclass du router V4).
# V6.8.1 : ContextPriority SUPPRIMÉ (contrat mort, §4 audit).
__all__ = [
    "AgentContext",
    "RoutingResult",
    "SearchResult",
    "SearchResponse",
    "FallbackDecision",
    "KnowledgeResult",
    "KnowledgeSearchResult",
    "ResolvedTools",
    "ActivityContextInfo",
    "SubjectContextInfo",
    "UserContextInfo",
    "ThreadContextInfo",
    "ContextStats",
    "BuiltContext",
]
