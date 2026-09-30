# V4 — Subject Registry & Context Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## ⚠️ CORRECTIONS ISSUES DE LA REVUE (appliquées pendant l'implémentation)

1. **BLOCKER** `tool_context.py` doit importer `app.subjects.tool_registry` (pas `app.context.tool_registry`).
2. **BLOCKER** `KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"` (knowledge dans `backend/app/knowledge`, retriever dans `backend/app/context/`).
3. **BLOCKER** Router : normalisation d'accents (unicodedata NFD fold) des deux côtés + topics/aliases français (fonctions, boucles, classes…). Sinon aucun matching français ne fonctionne.
4. Ambiguïté "réseaux" : les 2 entrées taxonomy (`computer_networks`, `neural_networks`) portent l'alias `reseaux` nu ; règle codée dans le router : ≥2 hits unsupported → **ambiguous** avec candidates. Les ids taxonomy déjà configurés dans le registry sont **exclus** de la détection unsupported (pas de collision configured/taxonomy). "reseaux informatiques"/"osi"/"tcp" restent des aliases du SubjectConfig configuré (pour les questions explicites) — seul `reseaux` nu est retiré du YAML configuré.
5. **§39** : le fill récent ne se déclenche QUE si la search n'a rien retourné, plafonné à 3 faits (identity + 2 plus récents). Sinon tous les intérêts sont injectés et le test qualité échoue.
6. `context["router"]` inclut `"subjects": routing.subjects` (multi_domain note non vide).
7. Frontend : type `SubjectContextInfo` restreint (le builder n'émet pas topics/knowledge_sources/tools_* — c'est SubjectOut de l'API list qui les porte).
8. Knowledge scoring : stop-words retirés des tokens requête, ≥1 token signifiant requis, seuil 0.3.
9. Typo `KNOWNEDGE` → aligné sur le texte réel émis par prompt_builder ; marker phrase exacte "Aucune connaissance de cours pertinente".
10. Route preview : `POST /api/subjects/preview/context` partout (overview inclus).
11. Knowledge dict sans matière : `"searched_sources": 0` inclus.
12. Frontend : TRACE_EVENTS à MERGER dans l'existant (pas remplacer) ; pas d'event KNOWLEDGE_UNAVAILABLE (le status est dans KNOWLEDGE_SEARCH extra).
13. Tests unitaires : helpers déclarés en tête ; assertions non tautologiques ; `membrane` attendu pour biologie.
14. thread_context : docstring alignée sur l'implémentation (métadonnées only, pas de contenu récent).
15. Aliases courts (`py`, `ip`) : matching par frontières de mots.
16. ContextPreviewRequest : validation UUID user_id comme ChatRequest.
17. Régression V3 : étape explicite re-run des checks mémoire V3 après implémentation (tools directs + cross-thread + dedup).
18. Événements ROUTING_*/KNOWLEDGE_* émis à chaque hop LLM (post-tool inclus) — bruit attendu, acceptable V4.


**Goal:** Transformer l'agent tuteur Python en moteur pédagogique central à contexte dynamique : Subject Registry piloté par configuration, Router avec hiérarchie de fallbacks, Knowledge Retrieval hiérarchique et Context Inspector — sans casser la V3.

**Architecture:** Un seul agent LangGraph ; le system prompt devient assemblé dynamiquement (Core Tutor générique + Subject Config + Knowledge pertinente + Tools + User Memory + Thread). Ajout d'un router par scoring de mots-clés (déterministe, sans LLM), d'un registre de matières YAML-driven, et d'un retriever de connaissances fichiers Markdown. Toute matière = 1 config + knowledge, zéro modification moteur.

**Tech Stack:** Python 3.14, FastAPI 0.139, LangGraph 1.2.11 (`create_agent` v1), PyYAML (à vérifier), React 19 + TS + Tailwind v4 + Framer Motion.

---

## Vue d'ensemble

```
backend/app/subjects/           (NOUVEAU)
├── __init__.py
├── schema.py                   SubjectConfig, TopicConfig, valid
├── registry.py                 chargement + lookup + statuses
├── definitions/                1 fichier = 1 matière (YAML)
│   ├── python.yaml
│   ├── biology.yaml
│   ├── mathematics.yaml
│   └── computer_networks.yaml
├── tool_registry.py            common/specialized, disponibilité réelle
└── taxonomy.py                 matières détectables non-configurées (unsupported)

backend/app/knowledge/          (NOUVEAU — fichiers .md seulement)
├── informatique/python/
│   ├── basics.md
│   ├── functions.md
│   ├── loops.md
│   └── oop.md
├── informatique/reseaux/
│   ├── osi_model.md
│   └── tcp_ip.md
├── sciences/biologie/
│   ├── cell.md
│   └── genetics.md
└── mathematics/algebre/
    └── equations.md

backend/app/context/
├── router.py                   (NOUVEAU) détection subject/topic/confidence/status
├── builder.py                  (MODIFIÉ) + subject, knowledge, tools, routing
├── knowledge_retriever.py      (NOUVEAU) search_knowledge + statuses
├── user_context.py             (MODIFIÉ) sélection par pertinence query
├── thread_context.py          (MODIFIÉ) résumé des N derniers messages
├── prompt_builder.py           (MODIFIÉ) blocs subject/knowledge/tools/routing
└── __init__.py                 (MODIFIÉ) exporte route_subject

backend/app/agent/
├── prompts.py                  (MODIFIÉ) CORE_PROMPT générique (plus "spécialisé Python")
└── middleware.py               (MODIFIÉ) wrap_model_call → router + build_context + prompt

backend/app/api/
├── subjects.py                 (NOUVEAU) GET /api/subjects, /{id}, /{id}/topics, POST /api/context/preview
├── schemas.py                  (MODIFIÉ) SubjectOut/TopicOut/ContextPreview req/resp
└── main.py                     (MODIFIÉ) inclure subjects.router

frontend/src/
├── types/agent.ts              (MODIFIÉ) SubjectInfo, RouterResult, ContextPreview
├── api/subjects.ts             (NOUVEAU) API client
├── components/memory/ContextInspectorCard.tsx  (NOUVEAU)
├── pages/MemoryPage.tsx        (MODIFIÉ) intégration ContextInspectorCard
├── components/tools/ToolStatusPanel.tsx        (MODIFIÉ) events routing
└── pages/LogsPage.tsx          (MODIFIÉ) tons ROUTING_*/KNOWLEDGE_*/TOOLS_*/SUBJECT_*

# Tests (scripts temporaires, nettoyés après)
backend/_v4_unit.py             tests unitaires sans LLM (router, registry, retriever, builders)
backend/_v4_tests.py            tests 1-10 + §39 via API réelle
```

---

## Task 1: Package `subjects/` — schéma + definitions

**Files:**
- Create: `backend/app/subjects/__init__.py`
- Create: `backend/app/subjects/schema.py`
- Create: `backend/app/subjects/definitions/python.yaml`
- Create: `backend/app/sections/definitions/biology.yaml` → NON, `backend/app/subjects/definitions/biology.yaml`
- Create: `backend/app/subjects/definitions/mathematics.yaml`
- Create: `backend/app/subjects/definitions/computer_networks.yaml`

- [ ] **Step 1: Vérifier PyYAML disponible**

```powershell
cd C:\Users\hp\Desktop\langchain\backend
python -c "import yaml; print(yaml.__version__)"
```
Expected: `6.0.x` ou similaire. Si erreur → `pip install pyyaml`.

- [ ] **Step 2: Écrire `subjects/schema.py`**

```python
# Schéma standard d'une matière — générique, aucun cas spécial
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
    aliases: list[str] = field(default_factory=list)  # déclencheurs router (minuscules)
    model: dict = field(default_factory=dict)         # {"provider", "name"} — réservé

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
        )


@dataclass
class TopicConfig:
    """Un topic d'une matière (hiérarchie domain > subject > topic)."""
    id: str
    subject_id: str
    name: str
    description: str = ""
```

- [ ] **Step 3: Écrire les 4 YAML de définition**

`definitions/python.yaml` (schéma §5 du brief, enrichi `topics`/`aliases` pour le router — ce sont des données de config, pas du code) :

```yaml
id: python
name: Python
domain: informatique
description: >
  Programmation avec le langage Python.
teaching_style:
  - pratique
  - progressif
  - orienté résolution de problèmes
pedagogical_guidelines:
  - commencer par un exemple concret
  - favoriser la pratique
  - donner des indices avant la solution
  - vérifier la compréhension
capabilities:
  - explain
  - exercise
  - quiz
  - evaluate
  - debug
  - review
tools:
  common:
    - create_exercise
    - evaluate_answer
    - give_hint
  specialized:
    - execute_python
    - analyze_python_error
knowledge:
  sources:
    - informatique/python/basics
    - informatique/python/functions
    - informatique/python/loops
    - informatique/python/oop
topics:
  - basics
  - variables
  - functions
  - return
  - loops
  - oop
  - classes
  - decorators
  - modules
  - async
aliases:
  - python
  - py
  - langage python
model:
  provider: ollama
  name: qwen2.5
```

`definitions/biology.yaml` :

```yaml
id: biology
name: Biologie
domain: sciences
description: >
  Science du vivant : cellule, génétique, écologie.
teaching_style:
  - visuel
  - analogies
pedagogical_guidelines:
  - utiliser des schémas décrits
  - relier structure et fonction
capabilities:
  - explain
  - quiz
  - evaluate
tools:
  common:
    - create_exercise
    - evaluate_answer
    - give_hint
  specialized:
    - analyze_diagram
knowledge:
  sources:
    - sciences/biologie/cell
    - sciences/biologie/genetics
topics:
  - cellule
  - membrane
  - mitochondrie
  - genetique
  - adn
  - ecologie
aliases:
  - biologie
  - biology
  - science du vivant
  - cellule
  - cellulaire
model:
  provider: ollama
  name: qwen2.5
```

`definitions/mathematics.yaml` :

```yaml
id: mathematics
name: Mathématiques
domain: sciences
description: >
  Algèbre, calcul, résolution d'équations.
teaching_style:
  - rigoureux
  - étape par étape
pedagogical_guidelines:
  - décomposer en sous-étapes
  - vérifier chaque étape
capabilities:
  - explain
  - exercise
  - evaluate
tools:
  common:
    - create_exercise
    - evaluate_answer
    - give_hint
  specialized:
    - verify_solution
    - symbolic_calculation
knowledge:
  sources:
    - mathematics/algebre/equations
topics:
  - algebre
  - equations
  - calcul
  - derivees
  - integrales
aliases:
  - mathematiques
  - maths
  - math
  - algebre
  - equation
model:
  provider: ollama
  name: qwen2.5
```

`definitions/computer_networks.yaml` :

```yaml
id: computer_networks
name: Réseaux informatiques
domain: informatique
description: >
  Réseaux : modèle OSI, TCP/IP, protocoles.
teaching_style:
  - progressif
  - couches par couches
pedagogical_guidelines:
  - partir du concret
  - remonter le modèle en couches
capabilities:
  - explain
  - quiz
  - evaluate
tools:
  common:
    - create_exercise
    - evaluate_answer
    - give_hint
  specialized: []
knowledge:
  sources:
    - informatique/reseaux/osi_model
    - informatique/reseaux/tcp_ip
topics:
  - osi
  - tcp
  - ip
  - protocoles
  - couches
  - dns
aliases:
  - reseaux informatiques
  - computer networks
  - osi
  - tcp ip
  - tcp/ip
  - protocole
  - dns
model:
  provider: ollama
  name: qwen2.5
```

- [ ] **Step 4: Écrire `subjects/__init__.py`**

```python
# Package subjects — Subject Registry piloté par configuration
from app.subjects.schema import SubjectConfig, TopicConfig

__all__ = ["SubjectConfig", "TopicConfig"]
```

- [ ] **Step 5: Vérifier chargement**

```powershell
python -c "from app.subjects.schema import SubjectConfig; print('ok')"
```
Expected: `ok` (exécuté depuis `backend/`).

---

## Task 2: `subjects/registry.py` + `taxonomy.py`

**Files:**
- Create: `backend/app/subjects/registry.py`
- Create: `backend/app/subjects/taxonomy.py`

- [ ] **Step 1: Écrire `registry.py`**

```python
# Subject Registry — matières chargées depuis definitions/*.yaml
# Ajouter une matière = 1 fichier YAML. Zéro modification moteur.
import threading
from pathlib import Path

import yaml

from app.logging.events import log_event
from app.subjects.schema import SubjectConfig

DEFINITIONS_DIR = Path(__file__).parent / "definitions"

_registry: dict[str, SubjectConfig] | None = None
_lock = threading.RLock()


def load_registry() -> dict[str, SubjectConfig]:
    """Charge toutes les definitions/*.yaml (singleton thread-safe)."""
    global _registry
    if _registry is not None:
        return _registry
    with _lock:
        if _registry is None:
            registry: dict[str, SubjectConfig] = {}
            for path in sorted(DEFINITIONS_DIR.glob("*.yaml")):
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    cfg = SubjectConfig.from_dict(data)
                    registry[cfg.id] = cfg
                except Exception as exc:
                    log_event(
                        "SUBJECT_REGISTRY_ERROR",
                        level="ERROR",
                        message=f"Failed to load {path.name}: {exc}",
                    )
            _registry = registry
            log_event(
                "SUBJECT_REGISTRY_LOADED",
                message=f"Registry loaded | subjects={sorted(registry.keys())}",
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
```

- [ ] **Step 2: Écrire `taxonomy.py` (matières non-configurées)**

```python
# Taxonomie des matières DÉTECTABLES mais non-configurées (fallback unsupported).
# La hiérarchie domain > subject > topic est déclarée en données.
from dataclasses import dataclass, field


@dataclass
class SubjectTaxonomy:
    id: str
    name: str
    domain: str
    aliases: list[str] = field(default_factory=list)


# Matières connues de la taxonomy SANS SubjectConfig → status "unsupported"
# (elles existent comme concepts mais sans guidelines/tools/knowledge)
UNSUPPORTED_SUBJECTS: list[SubjectTaxonomy] = [
    SubjectTaxonomy("astrophysique", "Astrophysique", "sciences",
                    ["astrophysique", "astronomie", "etoiles", "cosmos"]),
    SubjectTaxonomy("chimie", "Chimie", "sciences",
                    ["chimie", "molecules", "atomes"]),
    SubjectTaxonomy("histoire", "Histoire", "humanities",
                    ["histoire", "revolution", "guerre"]),
    SubjectTaxonomy("geographie", "Géographie", "humanities",
                    ["geographie", "cartographie"]),
    SubjectTaxonomy("anglais", "Anglais", "langues",
                    ["anglais", "english"]),
    SubjectTaxonomy("javascript", "JavaScript", "informatique",
                    ["javascript", "js", "node"]),
    SubjectTaxonomy("neural_networks", "Réseaux de neurones", "informatique",
                    ["reseaux de neurones", "neural networks", "reseau de neurones",
                     "deep learning", "apprentissage automatique", "machine learning"]),
]
```

- [ ] **Step 3: Vérifier**

```powershell
python -c "from app.subjects.registry import load_registry, get_subject; r = load_registry(); print(sorted(r.keys())); print(get_subject('python').domain)"
```
Expected: `['biology', 'computer_networks', 'mathematics', 'python']` puis `informatique`.

---

## Task 3: Fichiers Knowledge

**Files:**
- Create: `backend/app/knowledge/informatique/python/basics.md`
- Create: `backend/app/knowledge/informatique/python/functions.md`
- Create: `backend/app/knowledge/informatique/python/loops.md`
- Create: `backend/app/knowledge/informatique/python/oop.md`
- Create: `backend/app/knowledge/informatique/reseaux/osi_model.md`
- Create: `backend/app/knowledge/informatique/reseaux/tcp_ip.md`
- Create: `backend/app/knowledge/sciences/biologie/cell.md`
- Create: `backend/app/knowledge/sciences/biologie/genetics.md`
- Create: `backend/app/knowledge/mathematics/algebre/equations.md`

- [ ] **Step 1: Écrire les 9 fichiers Markdown (contenu pédagogique réel, structuré par sections `## topic-mot-clé`)**

Modèle pour chaque fichier — ex `functions.md` :

```markdown
# Python — Fonctions

## definition
Une fonction est un bloc de code réutilisable portant un nom...
[3-6 phrases pédagogiques]

## return
L'instruction return renvoie une valeur...
return termine l'exécution de la fonction...
Sans return explicite, une fonction renvoie None...

## parametres
Un paramètre est une variable dans la définition...
Un argument est la valeur passée à l'appel...
```

Les autres fichiers suivent le même modèle avec leurs sections propres : `basics.md` (variables, types, print, indentation), `loops.md` (for, while, range, break/continue), `oop.md` (classes, objets, méthodes, héritage, attributs), `osi_model.md` (couches, encapsulation, pdus), `tcp_ip.md` (tcp, ip, ports, three-way handshake), `cell.md` (membrane, organites, mitochondrie, noyau), `genetics.md` (adn, gènes, chromosomes, transcription), `equations.md` (résolution, inconnue, équations du premier degré).

**Important pour le retriever** : chaque fichier = un sujet ; chaque section `## <mot-clé>` = un topic récupérable indépendamment. Le retriever découpe par sections (pas par lignes) pour que chaque résultat ait un sens complet.

- [ ] **Step 2: Vérifier présence**

```powershell
Get-ChildItem -Recurse backend\app\knowledge -Filter *.md | Measure-Object | Select-Object Count
```
Expected: `Count : 9`.

---

## Task 4: Knowledge Retriever

**Files:**
- Create: `backend/app/context/knowledge_retriever.py`

- [ ] **Step 1: Écrire le retriever**

```python
# Knowledge Retriever — QUOI enseigner (le config dit COMMENT)
# search_knowledge(subject_id, topic, query) → sections pertinentes seulement.
# NE PAS charger tous les documents d'une matière (§7-§9 du brief).
import re
from pathlib import Path

from app.logging.events import log_event
from app.subjects.registry import get_subject

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

# Status possibles (§16) : found / insufficient / unavailable
STATUS_FOUND = "found"
STATUS_INSUFFICIENT = "insufficient"
STATUS_UNAVAILABLE = "unavailable"

_TOKEN_RE = re.compile(r"[a-z0-9àâçéèêëîïôùûü]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _available_sources(subject_id: str) -> list[Path]:
    """Fichiers knowledge réels d'une matière (sources déclarées + présentes)."""
    cfg = get_subject(subject_id)
    if cfg is None:
        return []
    files = []
    for src in cfg.knowledge.get("sources", []):
        p = KNOWLEDGE_DIR / f"{src}.md"
        if p.exists():
            files.append(p)
    return files


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Découpe un .md en sections (## topic). Retour [(topic, contenu)]."""
    sections = []
    current_topic = "_intro"
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                sections.append((current_topic, "\n".join(current_lines).strip()))
            current_topic = m.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_topic, "\n".join(current_lines).strip()))
    return sections


def search_knowledge(
    subject_id: str,
    topic: str | None = None,
    query: str = "",
    limit: int = 3,
) -> dict:
    """Recherche les sections knowledge pertinentes.

    Retourne :
    {
        "status": found|insufficient|unavailable,
        "items": [{"source", "topic", "content", "relevance"}],
        "searched_sources": int,
    }
    """
    query_tokens = _tokens(query or (topic or ""))
    items: list[dict] = []

    for path in _available_sources(subject_id):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        source_label = f"{path.parent.name}/{path.stem}"
        for sec_topic, sec_content in _split_sections(content):
            if not sec_content:
                continue
            # Scoring : overlap tokens section vs (topic + query)
            section_tokens = _tokens(f"{sec_topic} {sec_content[:400]}")
            if not query_tokens:
                # Pas de query exploitable → intro/overview du sujet
                score = 1.0 if sec_topic == "_intro" else 0.0
            else:
                overlap = len(query_tokens & section_tokens) / max(1, len(query_tokens))
                # bonus si le topic demandé correspond au nom de section
                if topic and topic.lower() in sec_topic:
                    overlap = min(1.0, overlap + 0.5)
                score = overlap
            if score >= 0.15:
                items.append({
                    "source": source_label,
                    "topic": sec_topic,
                    "content": sec_content,
                    "relevance": round(score, 2),
                })

    items.sort(key=lambda x: x["relevance"], reverse=True)
    items = items[:limit]

    n_sources = len(_available_sources(subject_id))
    if n_sources == 0:
        status = STATUS_UNAVAILABLE
    elif items:
        status = STATUS_FOUND
    else:
        status = STATUS_INSUFFICIENT

    log_event(
        "KNOWLEDGE_SEARCH",
        message=(
            f"Knowledge search | subject={subject_id} | topic={topic} | "
            f"status={status} | items={len(items)}"
        ),
        extra={
            "operation": "knowledge_search",
            "subject": subject_id,
            "topic": topic or "",
            "status": status,
            "items": len(items),
        },
    )
    return {"status": status, "items": items, "searched_sources": n_sources}
```

- [ ] **Step 2: Vérifier**

```powershell
python -c "from app.context.knowledge_retriever import search_knowledge; r = search_knowledge('python', 'return', 'comment fonctionne return en python'); print(r['status'], len(r['items']))"
```
Expected: `found 1` (section return de functions.md).

---

## Task 5: Router

**Files:**
- Create: `backend/app/context/router.py`

- [ ] **Step 1: Écrire le router (déterministe, sans LLM)**

```python
# Subject Router — détecte (subject, topic, confidence, status) d'une question.
# Déterministe : scoring de mots-clés sur aliases + topics des SubjectConfig.
# Statuts (§13) : supported / ambiguous / unsupported / unknown / multi_domain
import re
from dataclasses import dataclass, field

from app.logging.events import log_event
from app.subjects.registry import get_subject, list_subjects
from app.subjects.taxonomy import UNSUPPORTED_SUBJECTS

STATUS_SUPPORTED = "supported"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNSUPPORTED = "unsupported"
STATUS_UNKNOWN = "unknown"
STATUS_MULTI_DOMAIN = "multi_domain"

CONFIDENCE_SUPPORTED = 0.95   # alias direct + topic identifié
CONFIDENCE_TOPIC = 0.85       # alias direct sans topic
CONFIDENCE_UNSUPPORTED = 0.9  # matière taxonomy détectée non-configurée
CONFIDENCE_LOW = 0.3          # rien d'identifié

_WORD_RE = re.compile(r"[a-z0-9àâçéèêëîïôùûü/]+")


@dataclass
class RouterResult:
    subject: str | None
    topic: str | None
    confidence: float
    status: str
    candidates: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)  # multi_domain
    note: str = ""


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _phrase_in(text_lower: str, phrase: str) -> bool:
    """Alias multi-mots cherché comme sous-chaîne (normalisée)."""
    return phrase in text_lower


def route_subject(query: str, hint_subject: str | None = None) -> RouterResult:
    """Détermine la matière/topic d'une question.

    hint_subject : subject transmis explicitement (API preview, futur HITL).
    """
    log_event(
        "ROUTING_START",
        message=f"Routing | query={(query or '')[:80]}",
        extra={"operation": "routing", "query": (query or "")[:100]},
    )

    q_lower = (query or "").lower()
    q_words = _words(query or "")
    q_tokens = set(q_words)

    # 1) Hint explicite → supported si configuré
    if hint_subject:
        cfg = get_subject(hint_subject)
        if cfg:
            topic = _match_topic(cfg, q_words, q_lower)
            result = RouterResult(
                subject=cfg.id, topic=topic,
                confidence=CONFIDENCE_SUPPORTED if topic else CONFIDENCE_TOPIC,
                status=STATUS_SUPPORTED,
            )
            _emit_end(result)
            return result

    # 2) Scoring des matières configurées
    scores: dict[str, float] = {}
    topic_by_subject: dict[str, str | None] = {}
    for cfg in list_subjects():
        score = 0.0
        # alias phrase (multi-mots d'abord)
        for alias in sorted(cfg.aliases, key=len, reverse=True):
            if _phrase_in(q_lower, alias):
                score = max(score, 2.0)
        # topic direct
        topic = _match_topic(cfg, q_words, q_lower)
        if topic:
            score = max(score, 1.0)
            topic_by_subject[cfg.id] = topic
        else:
            topic_by_subject[cfg.id] = None
        if score > 0:
            scores[cfg.id] = score

    # 3) Détection unsupported (taxonomy)
    unsupported_hits: list[str] = []
    for taxo in UNSUPPORTED_SUBJECTS:
        for alias in taxo.aliases:
            if _phrase_in(q_lower, alias):
                unsupported_hits.append(taxo.id)
                break

    # 4) Décision
    if scores:
        best_id = max(scores, key=lambda k: scores[k])
        top = scores[best_id]
        second = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
        if len(scores) >= 2 and top == second and top >= 1.0:
            # Égalité parfaite entre matières configurées → ambiguous
            result = RouterResult(
                subject=None, topic=None,
                confidence=0.5, status=STATUS_AMBIGUOUS,
                candidates=sorted(scores.keys()),
            )
            _emit_end(result)
            return result
        cfg = get_subject(best_id)
        topic = topic_by_subject.get(best_id)
        result = RouterResult(
            subject=cfg.id, topic=topic,
            confidence=(CONFIDENCE_SUPPORTED if topic else CONFIDENCE_TOPIC) if top >= 2.0
            else (0.75 if topic else 0.6),
            status=STATUS_SUPPORTED,
        )
        _emit_end(result)
        return result

    if unsupported_hits:
        # Matière détectée mais non configurée → unsupported (fallback general tutor)
        result = RouterResult(
            subject=unsupported_hits[0], topic=None,
            confidence=CONFIDENCE_UNSUPPORTED,
            status=STATUS_UNSUPPORTED,
            candidates=unsupported_hits,
        )
        _emit_end(result)
        return result

    # 5) multi_domain : aucun alias, mais domaines multiples évoqués ?
    #    Pour V4 : détection identification seulement (§32)
    domain_hits = set()
    for cfg in list_subjects():
        if cfg.domain in q_tokens:
            domain_hits.add(cfg.domain)
    if len(domain_hits) >= 2:
        subs = [c.id for c in list_subjects() if c.domain in domain_hits]
        result = RouterResult(
            subject=None, topic=None, confidence=0.4,
            status=STATUS_MULTI_DOMAIN, subjects=subs,
        )
        _emit_end(result)
        return result

    # 6) Rien identifié → unknown (general tutor, pas de crash)
    result = RouterResult(
        subject=None, topic=None, confidence=CONFIDENCE_LOW,
        status=STATUS_UNKNOWN,
    )
    _emit_end(result)
    return result


def _match_topic(cfg, q_words: list[str], q_lower: str) -> str | None:
    """Topic de la config présent dans la question (mot ou phrase)."""
    for topic in cfg.topics:
        if " " in topic or "/" in topic:
            if _phrase_in(q_lower, topic):
                return topic
        elif topic.lower() in q_tokens_set(q_words):
            return topic
    return None


def q_tokens_set(q_words):
    return set(q_words)


def _emit_end(result: RouterResult) -> None:
    log_event(
        "ROUTING_END",
        message=(
            f"Routed | subject={result.subject} | topic={result.topic} | "
            f"status={result.status} | confidence={result.confidence}"
        ),
        extra={
            "operation": "routing",
            "subject": result.subject,
            "topic": result.topic,
            "status": result.status,
            "confidence": result.confidence,
            "candidates": result.candidates,
        },
    )
```

- [ ] **Step 2: Vérifier**

```powershell
python -c "from app.context.router import route_subject; r = route_subject('Explique-moi les fonctions Python.'); print(r.status, r.subject, r.topic, r.confidence)"
```
Expected: `supported python functions 0.95`.

---

## Task 6: Tool Registry

**Files:**
- Create: `backend/app/subjects/tool_registry.py`

- [ ] **Step 1: Écrire le tool registry**

```python
# Tool Registry — quels tools pour quelle matière, avec disponibilité RÉELLE.
# Un SubjectConfig déclare des tools ; le registry distingue implémentés/à venir.
from app.logging.events import log_event

# Tools réellement implémentés dans l'agent (couche langchain @tool)
IMPLEMENTED_TOOLS = {
    "additionner",
    "calculer_longueur_texte",
    "recherche_web",
    "get_user_profile",
    "update_user_profile",
    "get_user_memory",
    "save_user_memory",
    "update_user_memory",
    "delete_user_memory",
    "search_user_memory",
}

# Tools pédagogiques communs (déclarés dans les configs, non implémentés V4)
COMMON_PEDAGOGICAL_TOOLS = {
    "create_exercise": "Génère un exercice adapté",
    "evaluate_answer": "Évalue une réponse d'étudiant",
    "give_hint": "Donne un indice sans la solution",
}


def get_tools_for_subject(subject_id: str | None) -> dict:
    """Tools disponibles pour une matière.

    Retourne {"available": [tools implémentés utilisables],
              "declared_common": [...], "declared_specialized": [...],
              "available_count": int, "declared_count": int}
    """
    from app.subjects.registry import get_subject

    cfg = get_subject(subject_id) if subject_id else None

    # Base : tools réels de l'agent toujours disponibles
    available = sorted(IMPLEMENTED_TOOLS)
    declared_common: list[str] = []
    declared_specialized: list[str] = []

    if cfg:
        declared_common = list(cfg.tools.get("common", []))
        declared_specialized = list(cfg.tools.get("specialized", []))

    log_event(
        "TOOLS_SELECTED",
        message=(
            f"Tools selected | subject={subject_id} | "
            f"available={len(available)} | declared={len(declared_common) + len(declared_specialized)}"
        ),
        extra={
            "operation": "tools_selected",
            "subject": subject_id or "",
            "tools_available": available,
            "tools_declared": declared_common + declared_specialized,
        },
    )
    return {
        "available": available,
        "declared_common": declared_common,
        "declared_specialized": declared_specialized,
        "available_count": len(available),
        "declared_count": len(declared_common) + len(declared_specialized),
    }
```

- [ ] **Step 2: Vérifier**

```powershell
python -c "from app.subjects.tool_registry import get_tools_for_subject; r = get_tools_for_subject('python'); print(r['available_count'], r['declared_specialized'])"
```
Expected: `10 ['execute_python', 'analyze_python_error']`.

---

## Task 7: Core Prompt générique

**Files:**
- Modify: `backend/app/agent/prompts.py`

- [ ] **Step 1: Remplacer le CORE_PROMPT actuel**

```python
# Core Tutor Prompt — générique, valable pour TOUTES les matières.
# Le contenu spécifique (matière, guidelines, knowledge, tools) arrive
# dynamiquement via le Context/Prompt Builder — jamais ici.
CORE_PROMPT = """Tu es un tuteur adaptatif.

Ton objectif est d'aider l'étudiant à comprendre, raisonner
et devenir autonome.

## Règles générales

- adapter les explications au niveau de l'étudiant ;
- vérifier la compréhension avant d'approfondir ;
- favoriser les exemples concrets ;
- favoriser les exercices pratiques ;
- donner des indices avant de donner la solution ;
- ne jamais inventer d'informations ;
- utiliser les tools lorsqu'ils sont pertinents ;
- respecter le contexte de la matière fourni ci-dessous ;
- respecter les informations du profil utilisateur fournies ;
- n'utiliser que le contexte pertinent fourni ;
- signaler honnêtement les limites lorsque le contexte
  disponible est insuffisant.

## Identification

- user_id = identité PERSISTANTE de l'étudiant, identique dans
  toutes ses conversations. C'est ce user_id que tu dois passer
  aux tools de mémoire — jamais le thread_id.
- thread_id = la conversation ACTUELLE. Les messages d'un autre
  thread ne sont pas visibles ici.

## Mémoire longue durée — MemoryFacts

La mémoire de l'étudiant est composée de faits indépendants,
chacun dans une catégorie : identity, background, personality,
preference, interest. Ces faits persistent entre toutes ses
conversations. Des faits différents COEXISTENT.

Règles de LECTURE :

1. Le USER CONTEXT fourni dans ton prompt contient les faits
   pertinents — utilise-le d'abord. Consulte get_user_memory
   (category=None pour tout) si ce contexte est insuffisant.

2. search_user_memory retrouve des faits précis par requête.

Règles d'ÉCRITURE :

3. Utilise save_user_memory pour enregistrer UN fait durable
   QUAND l'étudiant le déclare explicitement (nom, formation,
   préférence d'apprentissage, centre d'intérêt durable,
   trait de caractère). Un fait par appel — jamais de fusion.

4. N'INVENTE JAMAIS. Ne prétends pas connaître des détails
   que la mémoire ne contient pas.

5. N'enregistre JAMAIS automatiquement :
   - les questions ordinaires ou demandes ponctuelles ;
   - le contenu d'un exercice ou d'une conversation ;
   - une hypothèse déduite du comportement
     ("il a demandé un exercice difficile" ne veut PAS dire
     "il aime les exercices difficiles").
   En cas de doute, n'enregistre pas.

6. update_user_memory (avec l'id) modifie UN fait précis ;
   delete_user_memory (avec l'id) en supprime UN seul.

## Gestion des matières (fournies par le système)

7. Si un SUBJECT CONTEXT est fourni ci-dessous, respecte ses
   guidelines pédagogiques et ses capacités.

8. Si le système signale une matière NON SPÉCIALISÉE
   (status unsupported/unknown), enseigne en tuteur général
   avec le Core seul, et indique proprement que le domaine
   n'est pas encore spécialisé.

9. Si une connaissance est marquée KNOWNEDGE UNAVAILABLE ou
   si le contexte est insuffisant, ne prétends jamais qu'elle
   vient de la base : dis-le et propose la recherche web
   (recherche_web) si pertinente.

10. Pour les questions ambiguës (plusieurs matières possibles),
    demande une clarification à l'étudiant au lieu de choisir
    arbitrairement.
"""

# Alias rétro-compatibilité
SYSTEM_PROMPT = CORE_PROMPT
```

- [ ] **Step 2: Vérifier l'import**

```powershell
python -c "from app.agent.prompts import CORE_PROMPT, SYSTEM_PROMPT; assert CORE_PROMPT == SYSTEM_PROMPT; assert 'tuteur adaptatif' in CORE_PROMPT; assert 'spécialisé en Python' not in CORE_PROMPT; print('ok')"
```

---

## Task 8: Context Builder V4

**Files:**
- Modify: `backend/app/context/builder.py`
- Modify: `backend/app/context/user_context.py`
- Modify: `backend/app/context/thread_context.py`

- [ ] **Step 1: Écrire le nouveau `builder.py`**

```python
# Context Builder V4 — assemble le contexte dynamique multi-sources.
# Séparation des responsabilités (§42) :
#   Router         → de quoi parle la question
#   Registry       → config de la matière
#   Retriever      → connaissances pertinentes
#   Tool Registry  → actions disponibles
#   User Memory    → durable user
#   Thread State   → conversation courante
#   Builder        = SÉLECTIONNE (ce module)
#   Prompt Builder = ASSEMBLE
from app.agent.memory import (
    list_facts,
    read_profile,
    search_facts,
)
from app.logging.events import log_event

from app.context.knowledge_retriever import search_knowledge
from app.context.router import RouterResult, route_subject
from app.context.thread_context import build_thread_context
from app.context.tool_context import build_tool_context  # wrapper tool_registry
from app.context.user_context import build_user_context
from app.subjects.registry import get_subject

__all__ = [
    "build_context",
    "build_user_context",
    "build_thread_context",
    "build_system_prompt",
]

from app.context.prompt_builder import build_system_prompt


def build_context(
    user_id: str,
    thread_id: str,
    query: str,
    subject: str | None = None,
    topic: str | None = None,
    max_memories: int = 12,
    max_knowledge: int = 3,
) -> dict:
    """Construit le contexte complet d'un appel LLM (V4 multi-sources).

    Retourne :
    {
        "router":   RouterResult dict (subject/topic/confidence/status),
        "subject":  SubjectConfig dict ou None (config de la matière),
        "knowledge": {"status", "items"} — sections pertinentes,
        "tools":    {"available", "declared_common", "declared_specialized"},
        "user":     {"text", "facts_count"},
        "thread":   {"thread_id", "message_count", "text"},
        "learning": None,  # réservé Learning Profile (V5+)
        "relevant_memories": [...],
        "stats":     observabilité,
    }

    Émet CONTEXT_BUILD_START / CONTEXT_BUILD_END + SELECTED_* par source.
    """
    log_event(
        "CONTEXT_BUILD_START",
        message=f"Context build start | user={user_id} | thread={thread_id}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "context_build", "query": (query or "")[:100]},
    )

    # --- 1. ROUTING ---
    routing = route_subject(query, hint_subject=subject)

    # --- 2. SUBJECT CONFIG ---
    subject_cfg = get_subject(routing.subject) if routing.subject else None
    if subject_cfg:
        log_event(
            "SUBJECT_CONTEXT_SELECTED",
            message=f"Subject config selected | subject={subject_cfg.id}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "subject_selected",
                "subject": subject_cfg.id,
                "domain": subject_cfg.domain,
                "guidelines_count": len(subject_cfg.pedagogical_guidelines),
            },
        )

    # --- 3. KNOWLEDGE (seulement si matière supportée) ---
    knowledge: dict = {"status": "unavailable", "items": []}
    if subject_cfg:
        knowledge = search_knowledge(
            subject_cfg.id,
            topic=routing.topic,
            query=query,
            limit=max_knowledge,
        )
        if knowledge["items"]:
            log_event(
                "KNOWLEDGE_SELECTED",
                message=(
                    f"Knowledge selected | subject={subject_cfg.id} | "
                    f"items={len(knowledge['items'])} | status={knowledge['status']}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "knowledge_selected",
                    "subject": subject_cfg.id,
                    "knowledge_items": [
                        f"{i['source']}/{i['topic']}" for i in knowledge["items"]
                    ],
                    "knowledge_status": knowledge["status"],
                },
            )

    # --- 4. TOOLS ---
    tools_ctx = build_tool_context(routing.subject)

    # --- 5. USER MEMORY (pertinence query + complément) ---
    relevant: list[dict] = []
    if query and query.strip():
        try:
            relevant = search_facts(user_id, query, limit=max_memories)
        except Exception:
            relevant = []
    if len(relevant) < max_memories:
        try:
            all_facts = list_facts(user_id)
        except Exception:
            all_facts = []
        have_ids = {f.get("id") for f in relevant}
        for f in reversed(all_facts):
            if len(relevant) >= max_memories:
                break
            if f.get("id") not in have_ids:
                relevant.append(f)

    try:
        profile = read_profile(user_id)
    except Exception:
        profile = {"name": None, "description": None}

    user_ctx = build_user_context(user_id, profile, relevant)

    # --- 6. THREAD STATE ---
    thread_ctx = build_thread_context(thread_id)

    context = {
        "router": {
            "subject": routing.subject,
            "topic": routing.topic,
            "confidence": routing.confidence,
            "status": routing.status,
            "candidates": routing.candidates,
        },
        "subject": (
            {
                "id": subject_cfg.id,
                "name": subject_cfg.name,
                "domain": subject_cfg.domain,
                "description": subject_cfg.description,
                "teaching_style": subject_cfg.teaching_style,
                "pedagogical_guidelines": subject_cfg.pedagogical_guidelines,
                "capabilities": subject_cfg.capabilities,
            }
            if subject_cfg
            else None
        ),
        "knowledge": knowledge,
        "tools": tools_ctx,
        "user": user_ctx,
        "thread": thread_ctx,
        "learning": None,
        "relevant_memories": relevant,
        "stats": {
            "memories_used": len(relevant),
            "knowledge_items": len(knowledge["items"]),
            "user_context_chars": len(user_ctx.get("text", "")),
            "context_size": (
                len(user_ctx.get("text", ""))
                + len(thread_ctx.get("text", ""))
                + sum(len(i["content"]) for i in knowledge["items"])
            ),
        },
    }

    log_event(
        "CONTEXT_BUILD_END",
        message=(
            f"Context built | user={user_id} | "
            f"subject={routing.subject} | status={routing.status} | "
            f"memories={len(relevant)} | knowledge={len(knowledge['items'])}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "context_build",
            "subject": routing.subject,
            "topic": routing.topic,
            "routing_status": routing.status,
            "memory_items": len(relevant),
            "knowledge_items": len(knowledge["items"]),
            "tools": tools_ctx["available_count"],
            "context_size": context["stats"]["context_size"],
            "user_memory_selected": [f.get("id") for f in relevant][:12],
            "thread_context_selected": bool(thread_ctx.get("thread_id")),
        },
    )
    return context
```

- [ ] **Step 2: Mettre à jour `user_context.py` (log sans doublon avec V3)**

Le code existant est conservé ; on ajoute en tête de `build_user_context` un commentaire de responsabilité. **Aucun changement fonctionnel** — USER_MEMORY_SELECTED est déjà émis. Ne pas modifier.

- [ ] **Step 3: Mettre à jour `thread_context.py` (N derniers messages résumés)**

```python
# Thread Context — résumé du thread courant SANS dupliquer l'historique.
# Le checkpointer fournit déjà les messages complets au LLM via LangGraph ;
# ce module ne fournit que les métadonnées + derniers échanges condensés.
from app.logging.events import log_event


def build_thread_context(thread_id: str, recent: int = 3) -> dict:
    """Résumé thread : id + NB messages + derniers messages condensés.

    "recent" : garde les N derniers échanges (résumés, tronqués) pour
    donner au LLM un ancrage conversationnel léger — jamais l'historique
    complet, jamais les messages d'un autre thread.
    """
    text = f"thread_id = {thread_id}" if thread_id else ""

    log_event(
        "THREAD_CONTEXT_SELECTED",
        message=f"Thread context | thread={thread_id} | recent={recent}",
        thread_id=thread_id,
        extra={
            "operation": "thread_context",
            "thread_id": thread_id,
            "duplicates_history": False,
        },
    )
    return {
        "thread_id": thread_id,
        "message_count": None,  # rempli par middleware si state dispo
        "recent": recent,
        "text": text,
    }
```

- [ ] **Step 4: Créer `tool_context.py` (wrapper léger, évite import circulaire tool_registry ↔ builder)**

```python
# Tool Context — wrapper de subjects/tool_registry pour le builder.
# Garde la séparation : builder ne connaît que cette interface.
from app.context.tool_registry import get_tools_for_subject


def build_tool_context(subject_id: str | None) -> dict:
    return get_tools_for_subject(subject_id)
```

**Placer tool_registry dans context/ plutôt que subjects/** — non : le brief demande `subject_config.tools` consultable ; on garde `subjects/tool_registry.py` et le wrapper dans `context/tool_context.py`. Vérifier absence d'import circulaire : `context/tool_context.py` → `subjects/tool_registry.py` → `subjects/registry.py` → OK, pas de cycle.

- [ ] **Step 5: Mettre à jour `context/__init__.py`**

```python
# Package context — Context Engineering (V4)
#
#   router            → subject/topic/status d'une question
#   build_context()   → sélectionne les infos pertinentes multi-sources
#   prompt_builder    → assemble le system prompt final
from app.context.builder import build_context, build_system_prompt
from app.context.router import route_subject

__all__ = ["build_context", "build_system_prompt", "route_subject"]
```

- [ ] **Step 5b: Vérifier imports**

```powershell
python -c "from app.context import build_context, route_subject; print('ok')"
```

---

## Task 9: Prompt Builder V4

**Files:**
- Modify: `backend/app/context/prompt_builder.py`

- [ ] **Step 1: Écrire le nouveau prompt_builder**

```python
# Prompt Builder V4 — assemble le system prompt dynamique.
# Structure (§24) : CORE + SUBJECT + TOPIC + USER + THREAD + KNOWLEDGE
#                  + TOOLS + LEARNING (réservé).
# Context Builder sélectionne ; Prompt Builder présente au modèle.
from app.logging.events import log_event


def build_system_prompt(
    core_prompt: str,
    context: dict,
    user_id: str = "",
    thread_id: str = "",
) -> str:
    """Assemble le system prompt final depuis le contexte structuré."""
    parts: list[str] = [core_prompt.strip()]

    # --- MATIÈRE (Subject Config) ---
    subject = context.get("subject")
    if subject:
        lines = [f"## MATIÈRE : {subject['name']} ({subject['domain']})"]
        if subject.get("description"):
            lines.append(subject["description"].strip())
        if subject.get("teaching_style"):
            lines.append("")
            lines.append("Style d'enseignement : " + ", ".join(subject["teaching_style"]))
        if subject.get("pedagogical_guidelines"):
            lines.append("")
            lines.append("Guidelines pédagogiques :")
            lines += [f"- {g}" for g in subject["pedagogical_guidelines"]]
        if subject.get("capabilities"):
            lines.append("")
            lines.append("Capacités : " + ", ".join(subject["capabilities"]))
        parts.append("\n".join(lines))

    # --- ROUTER NOTES (status non-supported → instructions) ---
    router = context.get("router") or {}
    status = router.get("status")
    if status == "unsupported":
        note = (
            "## NOTE DU SYSTÈME\n\n"
            f"La matière « {router.get('subject') or 'détectée'} » a été "
            "détectée mais n'a pas encore de configuration spécialisée. "
            "Enseigne en tuteur général et indique le clairement à "
            "l'étudiant."
        )
        parts.append(note)
    elif status == "ambiguous":
        cands = ", ".join(router.get("candidates") or [])
        note = (
            "## NOTE DU SYSTÈME\n\n"
            f"La question est ambiguë entre : {cands}. Demande une "
            "clarification à l'étudiant au lieu de choisir arbitrairement."
        )
        parts.append(note)
    elif status == "multi_domain":
        subs = ", ".join(router.get("subjects") or [])
        note = (
            "## NOTE DU SYSTÈME\n\n"
            f"Question multi-domaines ({subs}). Peux-tu clarifier le "
            "domaine principal visé par l'étudiant ?"
        )
        parts.append(note)

    # --- KNOWLEDGE ---
    knowledge = context.get("knowledge") or {}
    if knowledge.get("items"):
        lines = ["## CONNAISSANCES DU COURS (récupérées du knowledge)"]
        for item in knowledge["items"]:
            lines.append("")
            lines.append(f"### {item['source']} — {item['topic']}")
            lines.append(item["content"])
        parts.append("\n".join(lines))
    elif subject and knowledge.get("status") in ("insufficient", "unavailable"):
        note = (
            "## NOTE DU SYSTÈME\n\n"
            "Aucune connaissance de cours pertinente n'a été trouvée pour "
            "cette question. N'invente pas : enseigne avec tes "
            "connaissances générales, signale que ce contenu ne provient "
            "pas d'une base spécialisée, et propose recherche_web si "
            "pertinent."
        )
        parts.append(note)

    # --- USER CONTEXT ---
    user_text = (context.get("user") or {}).get("text", "")
    if user_text:
        parts.append(
            "## USER CONTEXT (mémoire longue durée de l'étudiant)\n\n" + user_text
        )

    # --- THREAD ---
    thread_text = (context.get("thread") or {}).get("text", "")
    if thread_text:
        parts.append("## Contexte courant\n\n" + thread_text)

    # --- LEARNING (réservé V5+) ---
    learning = context.get("learning")
    if learning:
        parts.append("## LEARNING CONTEXT\n\n" + str(learning))

    prompt = "\n\n".join(p for p in parts if p.strip())

    log_event(
        "PROMPT_BUILD",
        message=(
            f"Prompt built | user={user_id} | total_chars={len(prompt)} | "
            f"subject={router.get('subject')} | knowledge={len(knowledge.get('items', []))}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "prompt_build",
            "total_chars": len(prompt),
            "subject": router.get("subject"),
            "knowledge_items": len(knowledge.get("items", [])),
            "memories_used": len(context.get("relevant_memories") or []),
        },
    )
    return prompt
```

- [ ] **Step 2: Vérifier**

```powershell
python -c "
from app.context.prompt_builder import build_system_prompt
ctx = {
    'subject': {'id': 'python', 'name': 'Python', 'domain': 'informatique', 'description': 'Prog', 'teaching_style': ['pratique'], 'pedagogical_guidelines': ['exemples'], 'capabilities': ['explain']},
    'router': {'subject': 'python', 'topic': 'functions', 'confidence': 0.95, 'status': 'supported', 'candidates': []},
    'knowledge': {'status': 'found', 'items': [{'source': 'python/functions', 'topic': 'return', 'content': 'return renvoie...', 'relevance': 0.9}]},
    'user': {'text': 'Name:\nTest'},
    'thread': {'text': 'thread_id = t1'},
    'relevant_memories': [],
    'learning': None,
}
p = build_system_prompt('CORE', ctx, 'u', 't')
assert '## MATIÈRE : Python' in p and 'CONNAISSANCES DU COURS' in p and 'USER CONTEXT' in p
print(len(p), 'chars ok')"
```

---

## Task 10: Middleware V4

**Files:**
- Modify: `backend/app/agent/middleware.py` (wrap_model_call)

- [ ] **Step 1: Remplacer `wrap_model_call`**

Le bloc existant (lignes ~157-220) devient :

```python
    def wrap_model_call(self, request, handler):
        """Pipeline V4 : ROUTING → CONTEXT → PROMPT dynamique.

        Le Core Prompt de base (celui de l'agent) est remplacé par
        Core + MATIÈRE + KNOWLEDGE + USER + THREAD, assemblés par
        le Context/Prompt Builder. Fallback : Core seul si échec.
        """
        user_id, thread_id = _current_ids()

        if user_id:
            query = _last_user_query(request)

            base_prompt = (
                request.system_prompt
                or (
                    request.system_message.content
                    if request.system_message
                    else ""
                )
                or ""
            )
            core = base_prompt.split("## USER CONTEXT")[0].strip()
            # Fallback V3 → V4 : si le base contient déjà un bloc MATIÈRE
            # (tour précédent), on le retire aussi pour ne jamais dupliquer.
            core = core.split("## MATIÈRE")[0].strip()

            try:
                from app.agent.prompts import CORE_PROMPT
                from app.context import build_context, build_system_prompt

                context = build_context(
                    user_id=user_id,
                    thread_id=thread_id,
                    query=query,
                )
                new_prompt = build_system_prompt(
                    core_prompt=CORE_PROMPT,
                    context=context,
                    user_id=user_id,
                    thread_id=thread_id,
                )
            except Exception as exc:
                log_event(
                    "CONTEXT_BUILD_ERROR",
                    level="ERROR",
                    message=f"Context build failed, fallback core prompt: {exc}",
                    user_id=user_id,
                    thread_id=thread_id,
                    extra={"operation": "context_build", "error": str(exc)[:300]},
                )
                new_prompt = core

            request = request.override(system_prompt=new_prompt)

        return handler(request)
```

**Note importante** : le base_prompt de l'agent est `SYSTEM_PROMPT` (= `CORE_PROMPT`) ; on override TOUJOURS avec le prompt dynamique. Le `core` extrait sert uniquement de fallback si le builder échoue.

- [ ] **Step 2: Vérifier backend démarre**

```powershell
python -c "import app.main; print('imports ok')"
```

---

## Task 11: API subjects + context preview

**Files:**
- Modify: `backend/app/api/schemas.py` (ajouts)
- Create: `backend/app/api/subjects.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Schemas additionnels dans `schemas.py`**

Ajouter à la fin (après MemoryFactUpdate) :

```python
# ------------------------------------------------------------------
# V4 — Subjects & Context Preview
# ------------------------------------------------------------------


class SubjectOut(BaseModel):
    id: str
    name: str
    domain: str
    description: str
    teaching_style: list[str]
    pedagogical_guidelines: list[str]
    capabilities: list[str]
    topics: list[str]
    knowledge_sources: list[str]
    tools_common: list[str]
    tools_specialized: list[str]


class TopicOut(BaseModel):
    id: str
    subject_id: str
    name: str


class ContextPreviewRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    thread_id: str | None = None
    query: str = Field(..., min_length=1, max_length=2000)
    subject: str | None = Field(default=None, max_length=50)


class ContextPreviewResponse(BaseModel):
    router: dict
    subject: dict | None
    knowledge: dict
    tools: dict
    user: dict
    thread: dict
    prompt_preview: str
    stats: dict
```

- [ ] **Step 2: Écrire `api/subjects.py`**

```python
# Routes Subjects V4 — registry exposé en lecture + context preview (dev).
# context/preview expose des informations internes : réservé dev,
# protégé si exposé en production (§35).
from fastapi import APIRouter, HTTPException

from app.context import build_context, route_subject
from app.context.prompt_builder import build_system_prompt
from app.agent.prompts import CORE_PROMPT
from app.api.schemas import (
    ContextPreviewRequest,
    ContextPreviewResponse,
    SubjectOut,
    TopicOut,
)
from app.db.connections import init_db
from app.db.users import get_user
from app.subjects.registry import get_subject, list_subjects

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", response_model=list[SubjectOut])
def api_list_subjects() -> list[SubjectOut]:
    """Toutes les matières configurées (Subject Registry)."""
    out = []
    for cfg in list_subjects():
        out.append(SubjectOut(
            id=cfg.id, name=cfg.name, domain=cfg.domain,
            description=cfg.description,
            teaching_style=cfg.teaching_style,
            pedagogical_guidelines=cfg.pedagogical_guidelines,
            capabilities=cfg.capabilities,
            topics=cfg.topics,
            knowledge_sources=cfg.knowledge.get("sources", []),
            tools_common=cfg.tools.get("common", []),
            tools_specialized=cfg.tools.get("specialized", []),
        ))
    return out


@router.get("/{subject_id}", response_model=SubjectOut)
def api_get_subject(subject_id: str) -> SubjectOut:
    cfg = get_subject(subject_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Matière introuvable")
    return SubjectOut(
        id=cfg.id, name=cfg.name, domain=cfg.domain,
        description=cfg.description,
        teaching_style=cfg.teaching_style,
        pedagogical_guidelines=cfg.pedagogical_guidelines,
        capabilities=cfg.capabilities,
        topics=cfg.topics,
        knowledge_sources=cfg.knowledge.get("sources", []),
        tools_common=cfg.tools.get("common", []),
        tools_specialized=cfg.tools.get("specialized", []),
    )


@router.get("/{subject_id}/topics", response_model=list[TopicOut])
def api_subject_topics(subject_id: str) -> list[TopicOut]:
    cfg = get_subject(subject_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Matière introuvable")
    return [
        TopicOut(id=t, subject_id=cfg.id, name=t) for t in cfg.topics
    ]


# --- Context preview (outil dev, §35) ---


@router.post("/preview/context", response_model=ContextPreviewResponse)
def api_context_preview(payload: ContextPreviewRequest) -> ContextPreviewResponse:
    """Prévisualise le contexte + prompt SANS appeler le LLM.

    Route dev : expose la sélection interne (router, knowledge, mémoire).
    """
    init_db()
    if get_user(payload.user_id) is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    context = build_context(
        user_id=payload.user_id,
        thread_id=payload.thread_id or "",
        query=payload.query,
        subject=payload.subject,
    )
    prompt = build_system_prompt(
        core_prompt=CORE_PROMPT,
        context=context,
        user_id=payload.user_id,
        thread_id=payload.thread_id or "",
    )
    return ContextPreviewResponse(
        router=context["router"],
        subject=context["subject"],
        knowledge=context["knowledge"],
        tools=context["tools"],
        user=context["user"],
        thread=context["thread"],
        prompt_preview=prompt,
        stats=context["stats"],
    )
```

- [ ] **Step 3: Enregistrer le router dans `main.py`**

```python
from app.api import chat, health, logs, memory, subjects, threads, users
# ...
app.include_router(subjects.router)
```

- [ ] **Step 4: Vérifier démarrage**

```powershell
python -c "import app.main; print('ok')"
```

---

## Task 12: Tests unitaires V4 (sans LLM)

**Files:**
- Create: `backend/_v4_unit.py` (temporaire, supprimé au nettoyage)

- [ ] **Step 1: Écrire les tests unitaires**

```python
# Tests unitaires V4 — router, registry, retriever, builders (SANS LLM)
import sys

sys.path.insert(0, ".")
results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))


# ---- Registry ----
from app.subjects.registry import get_subject, list_subjects

subs = {s.id for s in list_subjects()}
check("registry: 4 matières", subs == {"python", "biology", "mathematics", "computer_networks"}, str(subs))
py = get_subject("python")
check("registry: python domain", py and py.domain == "informatique")
check("registry: python guidelines", len(py.pedagogical_guidelines) >= 3)
check("registry: inconnu → None", get_subject("astrophysique") is None)


# ---- Router ----
from app.context.router import (
    STATUS_SUPPORTED, STATUS_AMBIGUOUS, STATUS_UNSUPPORTED, STATUS_UNKNOWN,
)

r = route_subject_q("Explique-moi les fonctions Python.")
check("router: python/functions supported",
      r.status == STATUS_SUPPORTED and r.subject == "python" and r.topic == "functions",
      f"{r.status}/{r.subject}/{r.topic}")

r = route_subject_q("Explique-moi la membrane cellulaire.")
check("router: biology supported",
      r.status == STATUS_SUPPORTED and r.subject == "biology" and "cell" in (r.topic or ""),
      f"{r.status}/{r.subject}/{r.topic}")

r = route_subject_q("Explique-moi les réseaux.")
check("router: réseaux → ambiguous",
      r.status == STATUS_AMBIGUOUS and set(r.candidates) >= {"computer_networks", "neural_networks"} or r.status == STATUS_AMBIGUOUS,
      f"{r.status}/{r.candidates}")

r = route_subject_q("Explique-moi l'astrophysique.")
check("router: astrophysique unsupported",
      r.status == STATUS_UNSUPPORTED and r.subject == "astrophysique",
      f"{r.status}/{r.subject}")

r = route_subject_q("Quel temps fait-il demain ?")
check("router: unknown", r.status == STATUS_UNKNOWN, f"{r.status}/{r.subject}")

r = route_subject_q("Comment le cerveau a-t-il inspiré les réseaux de neurones artificiels ?")
check("router: multi/neural détecté",
      r.subject in ("neural_networks", None) or r.status in ("multi_domain", "ambiguous", "unsupported"),
      f"{r.status}/{r.subject}/{r.candidates}")


# ---- Knowledge retriever ----
from app.context.knowledge_retriever import search_knowledge

k = search_knowledge("python", "return", "comment fonctionne return en python")
check("knowledge: return trouvé", k["status"] == "found" and any(i["topic"] == "return" for i in k["items"]),
      f"{k['status']}/{[i['topic'] for i in k['items']]}")

k = search_knowledge("python", None, "explique les classes et l'héritage")
check("knowledge: oop/classes trouvé", k["status"] == "found", f"{k['status']}")

k = search_knowledge("python", None, " asyncio decorators métaprogrammation avancée")  # rien de pertinent
check("knowledge: insufficient si topic absent", k["status"] == "insufficient", k["status"])

k = search_knowledge("astrophysique", None, "trous noirs")
check("knowledge: unavailable si matière sans sources", k["status"] == "unavailable", k["status"])


# ---- Tool registry ----
from app.subjects.tool_registry import get_tools_for_subject

t = get_tools_for_subject("python")
check("tools: 10 dispo + 2 specialized", t["available_count"] == 10 and "execute_python" in t["declared_specialized"])
t = get_tools_for_subject(None)
check("tools: fallback sans matière", t["available_count"] >= 10)


# ---- Prompt builder ----
from app.context.prompt_builder import build_system_prompt

ctx = build_context_direct()
p = build_system_prompt("CORE", ctx)
check("prompt: MATIÈRE + KNOWLEDGE + USER", "## MATIÈRE" in p and "CONNAISSANCES" in p and "USER CONTEXT" in p)

ctx2 = {**ctx, "subject": None, "router": {"status": "unsupported", "subject": "astrophysique", "topic": None, "confidence": 0.9, "candidates": []}, "knowledge": {"status": "unavailable", "items": []}}
p2 = build_system_prompt("CORE", ctx2)
check("prompt: note unsupported présente", "pas encore de configuration spécialisée" in p2)


# ---- Helpers ----
def route_subject_q(q):
    from app.context.router import route_subject
    return route_subject(q)


def build_context_direct():
    return {
        "subject": {"id": "python", "name": "Python", "domain": "informatique",
                     "description": "d", "teaching_style": ["pratique"],
                     "pedagogical_guidelines": ["exemples"], "capabilities": ["explain"]},
        "router": {"subject": "python", "topic": "functions", "confidence": 0.95,
                    "status": "supported", "candidates": []},
        "knowledge": {"status": "found", "items": [
            {"source": "python/functions", "topic": "return", "content": "return renvoie", "relevance": 0.9}]},
        "user": {"text": "Name:\nX"},
        "thread": {"text": "thread_id = t"},
        "relevant_memories": [], "learning": None,
        "tools": {"available": [], "declared_common": [], "declared_specialized": [],
                   "available_count": 10, "declared_count": 5},
        "stats": {},
    }
```

**Note** : les `def` helpers sont référencés avant définition en Python module-level — réordonner : mettre `route_subject_q`/`build_context_direct` AVANT leur premier usage (le plan les liste en bas pour lisibilité ; lors de l'implémentation, les déclarer en tête).

- [ ] **Step 2: Exécuter**

```powershell
python _v4_unit.py
```
Expected: ~16 PASS, 0 FAIL.

- [ ] **Step 3: Corriger jusqu'à 0 FAIL**

Points sensibles prévisibles :
- "réseaux" seul doit matcher `computer_networks` (alias "reseaux informatiques" ne matche pas "les réseaux" seuls) ET `neural_networks` (alias "reseau de neurones" non plus) → il faut ajouter l'alias **`reseaux`** aux DEUX configs pour créer l'ambiguïté intentionnelle (§14) ;
- "membrane cellulaire" : alias biology contient "cellulaire" et "cellule" → supported ;
- "cerveau + réseaux de neurones" : "reseau de neurones" alias → unsupported (neural détecté non configuré) — acceptable pour V4 (identification du multi-domaine passe par la clarification LLM).

**Actions correctives** :
1. Ajouter `reseaux` aux aliases de `computer_networks.yaml` ET ajouter `SubjectTaxonomy("neural_networks", ...)` avec alias `reseaux` (déjà présent) → "Explique-moi les réseaux" touchera les deux → mais unsupported a priorité sur ambiguous... **À gérer** : dans le router, si unsupported_hits ET scores configurés existent → laisser le configured l'emporter (supported) ; pour le cas ambigu pur (deux unsupported ou configured+unsupported égaux), retourner ambiguous. Décision : "réseaux" → computer_networks (configured, score 2.0 via alias) vs neural_networks (unsupported) → **supported computer_networks**. MAIS le brief exige ambiguous pour "Explique-moi les réseaux". **Meilleure solution** : retirer "reseaux" nu des aliases de computer_networks ; créer deux taxonomy entries détectables non-configurées `computer_networks_taxo` et `neural_networks_taxo` avec alias partagé "reseaux" → route_subject("Explique-moi les réseaux") → aucun configured hit, DEUX unsupported hits → si ≥2 unsupported hits → **ambiguous** avec candidates=[computer_networks, neural_networks]. Implémentation dans router : après unsupported_hits, `if len(unsupported_hits) >= 2 → ambiguous`.
2. Ajouter dans taxonomy : `SubjectTaxonomy("computer_networks", "Réseaux informatiques", "informatique", ["reseaux"])` et neural_networks garde "reseaux de neurones", "reseau de neurones", "neural networks", "deep learning", "machine learning" SANS "reseaux" seul.

- [ ] **Step 4: Re-exécuter jusqu'à 0 FAIL**


## Task 13: Tests d'intégration 1–10 + §39 (API réelle)

**Files:**
- Create: `backend/_v4_tests.py` (temporaire)

- [ ] **Step 1: Démarrer le backend**

```powershell
python -m uvicorn app.main:app --port 8000
```
Vérifier : `Invoke-RestMethod http://127.0.0.1:8000/api/health`.

- [ ] **Step 2: Écrire et exécuter le script de tests**

Structure du script (même pattern que V3 `_tests_v3_abdefgh.py`) : setup users/threads, puis :

| Test | Appel | Vérifications |
|---|---|---|
| 1 Python | chat "Explique-moi les fonctions Python." | logs ROUTING_END subject=python topic=functions status=supported ; réponse parle de fonctions |
| 2 Biologie | chat "Explique-moi la membrane cellulaire." | subject=biology status=supported ; KNOWLEDGE_SELECTED items>0 (cell.md) |
| 3 Ambiguïté | chat "Explique-moi les réseaux." | status=ambiguous ; réponse DU LLM demande clarification |
| 4 Inconnu | chat "Explique-moi l'astrophysique." | status=unsupported ; réponse indique domaine non spécialisé (pas de crash) |
| 5 Knowledge absent | chat "Explique-moi les décorateurs et asyncio en Python." | subject=python supported + knowledge_status=insufficient ; réponse honnête (pas de prétention de source) |
| 6 Mémoire sélectionnée | POST /api/subjects/preview/context avec user V3 connu | user.facts_count ≥ 1 ; USER_MEMORY_SELECTED dans logs |
| 7 Thread isolation | 2 threads même user, preview chacun | thread.thread_id différents ; user identique |
| 8 Cross-thread | user A sur thread2 "Que sais-tu de moi ?" | mémoire user dispo, thread différent → réponse correcte |
| 9 Isolation | user B preview | facts de A absents |
| 10 Contexte minimal | preview query "2+2 ?" avec user sans mémoire | memories_used == 0 |
| §39 Qualité | user avec 5+ faits (robotique, aéronautique, mécatronique, préférences, description) + preview "Explique les fonctions Python." | memories_selected ⊆ {préférences, éventuellement 1-2 pertinents} — tous les intérêts NON injectés |

- [ ] **Step 3: Exécuter, corriger, itérer jusqu'à tous PASS**

Seuils réalistes (LLM) : tests 3/4 vérifient la présence de mots de clarification/limite dans la réponse (ex: "précises", "clair", "spécialisé", "limites") — assouplir si Gemma formule autrement, mais ROUTING_END dans les logs doit être exact.

- [ ] **Step 4: Nettoyer**

```powershell
Remove-Item _v4_unit.py, _v4_tests.py -ErrorAction SilentlyContinue
```

---

## Task 14: Frontend — Types, API, Context Inspector

**Files:**
- Modify: `frontend/src/types/agent.ts`
- Create: `frontend/src/api/subjects.ts`
- Create: `frontend/src/components/memory/ContextInspectorCard.tsx`
- Modify: `frontend/src/pages/MemoryPage.tsx`
- Modify: `frontend/src/components/tools/ToolStatusPanel.tsx`
- Modify: `frontend/src/pages/LogsPage.tsx`

- [ ] **Step 1: Types (types/agent.ts)**

```typescript
// ---- V4 Subjects & Context ----

export interface SubjectInfo {
  id: string;
  name: string;
  domain: string;
  description: string;
  teaching_style: string[];
  pedagogical_guidelines: string[];
  capabilities: string[];
  topics: string[];
  knowledge_sources: string[];
  tools_common: string[];
  tools_specialized: string[];
}

export interface RouterInfo {
  subject: string | null;
  topic: string | null;
  confidence: number;
  status: 'supported' | 'ambiguous' | 'unsupported' | 'unknown' | 'multi_domain';
  candidates: string[];
  subjects?: string[];
}

export interface KnowledgeItem {
  source: string;
  topic: string;
  content: string;
  relevance: number;
}

export interface ContextPreview {
  router: RouterInfo;
  subject: SubjectInfo | null;
  knowledge: { status: string; items: KnowledgeItem[]; searched_sources: number };
  tools: { available: string[]; declared_common: string[]; declared_specialized: string[]; available_count: number; declared_count: number };
  user: { text: string; facts_count: number };
  thread: { thread_id: string; message_count: number | null; text: string };
  prompt_preview: string;
  stats: Record<string, number>;
}
```

- [ ] **Step 2: API client (`api/subjects.ts`)**

```typescript
// API Subjects — registry + context preview (V4)
import type { ContextPreview, SubjectInfo } from '../types/agent';
import { apiFetch } from './base';

export async function listSubjects(): Promise<SubjectInfo[]> {
  return apiFetch<SubjectInfo[]>('/api/subjects');
}

export async function previewContext(payload: {
  user_id: string;
  thread_id?: string;
  query: string;
  subject?: string;
}): Promise<ContextPreview> {
  return apiFetch<ContextPreview>('/api/subjects/preview/context', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 3: `ContextInspectorCard.tsx`**

Composant avec : champ query + bouton Preview → appelle `previewContext` (user courant + thread courant) → affiche :
- **Current Subject** : badges status (couleur par status), domain/subject/topic/confidence ;
- Sections extensibles (details/summary ou state local) : User Context, Thread Context, Subject Config, Knowledge (sources + topics + relevance), Tools (available vs declared), Prompt (pre scrollable).

Style : suivre LongTermMemoryCard (surface/border/mono, tailwind tokens, framer-motion layout). Header : icône `Layers`/`Network` + "Context Inspector" + sous-titre "routing · context · prompt".

- [ ] **Step 4: Intégrer dans MemoryPage (après LongTermMemoryCard)**

```tsx
<ContextInspectorCard
  userId={currentUser?.user_id ?? null}
  threadId={currentThread?.thread_id ?? null}
/>
```

- [ ] **Step 5: ToolStatusPanel + LogsPage — nouveaux events**

ToolStatusPanel TRACE_EVENTS :
```typescript
ROUTING_START: { label: 'routing', depth: 0 },
ROUTING_END: { label: 'routed', depth: 0 },
KNOWLEDGE_SEARCH: { label: 'knowledge search', depth: 1 },
KNOWLEDGE_SELECTED: { label: 'knowledge selected', depth: 1 },
TOOLS_SELECTED: { label: 'tools selected', depth: 1 },
SUBJECT_CONTEXT_SELECTED: { label: 'subject selected', depth: 1 },
SUBJECT_REGISTRY_LOADED: { label: 'registry loaded', depth: 0 },
```
(Routing tones : supported/success green ; ambiguous/unknown muted/amber.)

LogsPage EVENT_TONES :
```typescript
ROUTING_START: 'text-[#6c63ff]',
ROUTING_END: 'text-[#22c55e]',
KNOWLEDGE_SEARCH: 'text-[#6c63ff]',
KNOWLEDGE_SELECTED: 'text-[#22c55e]',
KNOWLEDGE_UNAVAILABLE: 'text-[#f59e0b]',
TOOLS_SELECTED: 'text-[#6c63ff]',
SUBJECT_CONTEXT_SELECTED: 'text-[#6c63ff]',
SUBJECT_REGISTRY_LOADED: 'text-[#f59e0b]',
SUBJECT_REGISTRY_ERROR: 'text-[#ef4444]',
```

- [ ] **Step 6: Build**

```powershell
cd frontend; npm run build
```
Expected: 0 erreur TS.

---

## Task 15: Rapport V4

**Files:**
- Modify: `RAPPORT.md`

- [ ] **Step 1: Ajouter la section V4** avec : architecture (diagramme flux complet §43), schémas documentés (SubjectConfig, RouterResult, KnowledgeItem, ToolContext, Context), mémoire (user vs thread), les 6 cas de fallback (supported/ambiguous/unknown/unsupported/knowledge unavailable/tool unavailable) avec comportements réels observés, nouveaux événements (tableau), résultats des 10 tests + §39 + tests unitaires, compatibilité future (Learning Profile, Learning Engine, RAG, multi-agent, HITL, multi-modèle, 20+ matières — chaque point avec la porte d'entrée concrète dans le code).

- [ ] **Step 2: Vérifier cohérence avec les 16 critères de réussite (§46)**

---

## Ordre d'exécution & checkpoints

1. Tasks 1-2 (registry) → checkpoint : registry charge 4 matières
2. Task 3 (knowledge files) → checkpoint : 9 fichiers
3. Task 4 (retriever) → checkpoint : search_knowledge('python','return',...) = found
4. Task 5 (router) → checkpoint : route "fonctions Python" = supported/python/functions
5. Tasks 6-9 (tool registry, prompt, builder, prompt_builder) → checkpoint : imports ok
6. Task 10 (middleware) → checkpoint : `import app.main` ok
7. Task 11 (API) → checkpoint : GET /api/subjects renvoie 4
8. Task 12 (unit tests) → checkpoint : 16/16
9. Task 13 (tests intégration) → checkpoint : 10/10 + §39
10. Task 14 (frontend) → checkpoint : build 0 erreur
11. Task 15 (rapport)

**Règles transverses** : jamais de cache de module singleton cassé (invalidate dans tests), logs STRUCTURÉS via log_event existant, tout échec de routing/knowledge = situation NORMALE loggée (jamais exception 500), sandbox `danger-full-access` + justification pour chaque commande pwsh (pattern établi session).
