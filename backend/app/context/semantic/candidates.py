# Topic Candidates V7.1 (mission §8/§12) — représentations
# sémantiques construites à partir des DONNÉES DÉCLARATIVES
# existantes. AUCUN synonyme codé en Python, aucun if subject.
#
# Sources (toutes déclaratives) :
#   - SubjectConfig : id, name, domain, description, aliases
#   - SubjectConfig.topics : liste des topics (noms)
#   - SubjectConfig.knowledge sources : titres H1 des fichiers .md
#   - SubjectConfig semantic_terms (V7.1, optionnel) : dict
#     {topic: [termes...]} — description sémantique FR/EN du
#     concept, ÉCRITE EN YAML par l'auteur de la matière, pas en
#     code. C'est la voie déclarative pour les paraphrases
#     (« une fonction qui s'appelle elle-même » ↔ recursion).
#
# Représentation candidate (mission §12) : PAS des mots isolés —
#   topic name + description + aliases + semantic_terms + titres
#   knowledge → UNE phrase composite embeddée.
from __future__ import annotations

from dataclasses import dataclass, field

from app.subjects.registry import list_subjects
from app.subjects.schema import SubjectConfig

# Cache des candidats (invalidé quand le registry est rechargé —
# invalidation par compteur de version du registry).
_cache: dict | None = None
_cache_registry_state: tuple | None = None


@dataclass
class TopicCandidate:
    """UN candidat routable (matière + topic éventuel).

    subject toujours présent ; topic None = la matière entière.
    text = phrase composite déclarative qui SERA embeddée.
    concept_key = signature du CONCEPT (§11) : deux topics
    déclarant les MÊMES semantic_terms (ex: boucles/loops,
    double déclaration FR/EN) sont le MÊME concept — jamais
    une ambiguïté, jamais deux candidats concurrents.
    """

    subject: str
    topic: str | None
    text: str
    subject_name: str = ""
    aliases: list[str] = field(default_factory=list)
    # signature déclarATIVE pure (semantic_terms YAML) : deux
    # topics déclarant les MÊMES terms = MÊME concept, même si
    # leurs textes composites divergent (stem knowledge, nom).
    key_terms: list[str] = field(default_factory=list)

    @property
    def concept_key(self) -> str:
        # SIGNATURE DES semantic_terms (§11) : deux topics
        # déclarant les MÊMES semantic_terms = MÊME concept
        # (boucles/loops : double déclaration FR/EN de l'auteur).
        # La clé ignore le nom du topic, l'ordre, les répétitions
        # et les stems knowledge. Aucune paire codée en dur ;
        # topics sans semantic_terms retombent sur le texte
        # composite (restent distincts).
        if self.key_terms:
            toks = {
                t
                for term in self.key_terms
                for t in term.lower().split()
                if t
            }
            return " ".join(sorted(toks))
        head = f"{self.subject}|{self.text}"
        if self.topic:
            head = head.replace(self.topic, "", 1)
        return _strip_key(head)

    def label(self) -> str:
        if self.topic:
            return f"{self.subject}/{self.topic}"
        return self.subject


def _topic_semantic_terms(
    cfg: SubjectConfig, topic: str
) -> list[str]:
    """semantic_terms[topic] du YAML — VOIE DÉCLARATIVE V7.1.

    Format YAML accepté (les deux, générique) :
      semantic_terms:
        recursion:
          - fonction qui s appelle elle meme
          - récursivité recursion appel de soi
        loops:
          - répéter une action plusieurs fois
          - boucle iterate repeat for while
    """
    raw = cfg.semantic_terms.get(topic) if cfg.semantic_terms else None
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(t) for t in raw if t]
    return []


def _subject_candidate(cfg: SubjectConfig) -> TopicCandidate:
    """Représentation de la MATIÈRE entière (mission §12)."""
    parts = [cfg.id, cfg.name, cfg.domain]
    if cfg.description:
        parts.append(cfg.description)
    parts.extend(cfg.aliases)
    return TopicCandidate(
        subject=cfg.id,
        topic=None,
        text=" ; ".join(p for p in parts if p),
        subject_name=cfg.name,
        aliases=list(cfg.aliases),
    )


def _strip_key(text: str) -> str:
    """Clé de concept normalisée : ENSEMBLE TRIÉ des tokens
    (dédoublonnés) — insensible à l'ordre et aux répétitions.
    Ex: "repeter action fois repeter" ≡ "action fois repeter"."""
    toks = {
        t for t in text.lower().replace(";", " ").split() if t
    }
    return " ".join(sorted(toks))


def _topic_candidates(cfg: SubjectConfig) -> list[TopicCandidate]:
    """Représentations par TOPIC — topic + semantic_terms YAML +
    titres H1 knowledge (§8 : topic name + description + aliases
    + knowledge title)."""
    out: list[TopicCandidate] = []
    for topic in cfg.topics:
        parts: list[str] = [topic, cfg.name]
        if cfg.description:
            parts.append(cfg.description)
        parts.extend(_topic_semantic_terms(cfg, topic))
        # titres H1 des fichiers knowledge (titre lisible)
        for src in cfg.knowledge.get("sources", []):
            stem = src.rsplit("/", 1)[-1]
            # un fichier knowledge peut couvrir plusieurs topics :
            # on l'ajoute seulement si son stem apparaît dans le
            # topic (ex: functions.md ↔ topics functions/fonctions)
            if stem and stem.lower() in topic.lower():
                parts.append(stem.replace("_", " "))
                break
        out.append(
            TopicCandidate(
                subject=cfg.id,
                topic=topic,
                text=" ; ".join(p for p in parts if p),
                subject_name=cfg.name,
                aliases=list(cfg.aliases),
                key_terms=_topic_semantic_terms(cfg, topic),
            )
        )
    return out


def build_topic_candidates() -> list[TopicCandidate]:
    """TOUS les candidats routables du Registry — GÉNÉRIQUE.

    Ajouter une matière (YAML) ajoute automatiquement ses
    candidats : ZÉRO modification de code (test no-hardcode §25).
    Cache invalidé si le registry est rechargé (tests invalidate()).
    """
    global _cache, _cache_registry_state
    subjects = list_subjects()
    # état observable du registry pour invalider le cache
    state = tuple(
        (c.id, tuple(c.topics), tuple(c.aliases)) for c in subjects
    )
    if _cache is not None and state == _cache_registry_state:
        return _cache
    cands: list[TopicCandidate] = []
    for cfg in subjects:
        cands.append(_subject_candidate(cfg))
        cands.extend(_topic_candidates(cfg))
    # DÉDUPLICATION DE CONCEPTS (§11) : deux topics déclarant le
    # même concept (semantic_terms identiques — ex: boucles/loops)
    # ne produisent QU'UN candidat (le premier en ordre YAML,
    # choix de l'auteur de la matière). Zéro paire codée en dur.
    seen_concepts: set[tuple[str, str]] = set()
    deduped: list[TopicCandidate] = []
    for c in cands:
        key = (c.subject, c.concept_key)
        if key in seen_concepts:
            continue
        seen_concepts.add(key)
        deduped.append(c)
    _cache = deduped
    _cache_registry_state = state
    return deduped


def invalidate_candidates_cache() -> None:
    """Force le rechargement des candidats (tests)."""
    global _cache, _cache_registry_state
    _cache = None
    _cache_registry_state = None


__all__ = [
    "TopicCandidate",
    "build_topic_candidates",
    "invalidate_candidates_cache",
]
