# Taxonomie des matières DÉTECTABLES mais non-configurées (fallback unsupported).
# La hiérarchie domain > subject > topic est déclarée en données.
# IMPORTANT : un id déjà présent dans le Subject Registry est EXCLU de la
# détection unsupported (pas de collision configured/taxonomy).
from dataclasses import dataclass, field


@dataclass
class SubjectTaxonomy:
    id: str
    name: str
    domain: str
    aliases: list[str] = field(default_factory=list)


# Matières connues de la taxonomy SANS SubjectConfig → status "unsupported".
# NB : "computer_networks" et "neural_networks" partagent l'alias "reseaux"
# (nu) : "Explique-moi les réseaux" → 2 hits → status "ambiguous" (§14).
UNSUPPORTED_SUBJECTS: list[SubjectTaxonomy] = [
    SubjectTaxonomy(
        "computer_networks",
        "Réseaux informatiques",
        "informatique",
        ["reseaux"],
    ),
    SubjectTaxonomy(
        "neural_networks",
        "Réseaux de neurones",
        "informatique",
        [
            "reseaux",
            "reseaux de neurones",
            "reseau de neurones",
            "neural networks",
            "deep learning",
            "apprentissage automatique",
            "machine learning",
        ],
    ),
    SubjectTaxonomy(
        "astrophysique",
        "Astrophysique",
        "sciences",
        ["astrophysique", "astronomie", "etoiles", "cosmos"],
    ),
    SubjectTaxonomy(
        "chimie", "Chimie", "sciences",
        ["chimie", "molecules", "atomes"],
    ),
    SubjectTaxonomy(
        "histoire", "Histoire", "humanities",
        ["histoire", "revolution", "guerre mondiale"],
    ),
    SubjectTaxonomy(
        "geographie", "Géographie", "humanities",
        ["geographie", "cartographie"],
    ),
    SubjectTaxonomy(
        "anglais", "Anglais", "langues",
        ["anglais", "english"],
    ),
    SubjectTaxonomy(
        "javascript", "JavaScript", "informatique",
        ["javascript", "js", "node"],
    ),
]


def active_taxonomy(registry_ids: set[str]) -> list[SubjectTaxonomy]:
    """Entrées taxonomy actives = ids NON déjà configurés (anti-collision)."""
    return [t for t in UNSUPPORTED_SUBJECTS if t.id not in registry_ids]
