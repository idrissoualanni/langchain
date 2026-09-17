# Schéma standard d'une matière — générique, aucun cas spécial codé
from dataclasses import dataclass, field


@dataclass
class SubjectConfig:
    """Configuration d'UNE matière. Le moteur ne connaît que ce schéma."""
    id: str
    name: str
    domain: str                      # ex: informatique, sciences
    description: str = ""
    teaching_style: list[str] = field(default_factory=list)
    pedagogical_guidelines: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    tools: dict = field(default_factory=dict)        # {"common": [...], "specialized": [...]}
    knowledge: dict = field(default_factory=dict)    # {"sources": [...]}
    topics: list[str] = field(default_factory=list)   # topics connus (routing)
    aliases: list[str] = field(default_factory=list)  # déclencheurs router (normalisés)
    model: dict = field(default_factory=dict)         # {"provider", "name"} — réservé
    # V7.1 : description sémantique PAR TOPIC — voie déclarative
    # des paraphrases (mission §8) : {topic: [termes FR/EN...]}
    semantic_terms: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "SubjectConfig":
        return cls(
            id=data["id"],
            name=data["name"],
            domain=data.get("domain", ""),
            description=data.get("description", ""),
            teaching_style=data.get("teaching_style", []),
            pedagogical_guidelines=data.get("pedagogical_guidelines", []),
            capabilities=data.get("capabilities", []),
            tools=data.get("tools", {}),
            knowledge=data.get("knowledge", {}),
            topics=data.get("topics", []),
            aliases=data.get("aliases", []),
            model=data.get("model", {}),
            semantic_terms=data.get("semantic_terms", {}) or {},
        )


@dataclass
class TopicConfig:
    """Un topic d'une matière (hiérarchie domain > subject > topic)."""
    id: str
    subject_id: str
    name: str
    description: str = ""
