# Plan — Câblage des subgraphs orphelins, transport du workflow hint, couche MCP, composer

## Contexte (analyse préalable)

3 subgraphs implémentés mais **jamais invoqués** : `research`, `coding`, `video`
(`grep` des importeurs externes à `subgraphs/` → seul `problem` est consommé).
`WIRED_WORKFLOWS` est incomplet. Le composer expose des `@mentions`
(`use-composer-mentions.ts`) qui ne transitent **jamais** jusqu'au routeur
(`ChatRequest` n'a pas de champ dédié). La couche MCP décrite par la doc
(§39–§41) est **absente** du backend. `langchain-mcp-adapters` 0.3.2 +
`mcp` 1.29 + `FastMCP` sont installés et utilisables.

Objectif : `@deep-research` / `@video` / `@code` / `@agenda` / `@exercise`
dans le composer déclenchent **réellement** le subgraph correspondant.

---

## 1. Transport du workflow hint (frontend → routeur)

**Problème** : `ChatRequest` ne porte que `{user_id, thread_id, message, model}`.
Le hint du composer n'arrive jamais au backend.

### 1a. Contrat API — `backend/app/api/schemas.py`

Ajouter à `ChatRequest` :

```python
workflow: str | None = Field(
    default=None, max_length=50,
    description="Hint de workflow émis par le composer (@mention) — "
                "validé contre KNOWN_WORKFLOWS, ignoré si inconnu",
)
```

### 1b. API — `backend/app/api/chat.py`

`api_chat` et `api_chat_stream` passent `workflow=payload.workflow` à
`run_agent` / `run_agent_stream`.

### 1c. Runner — `backend/app/agent/runner.py`

- `run_agent(..., workflow: str | None = None)`
- `run_agent_stream(..., workflow: str | None = None)`
- `_build_input(..., workflow)` → ajoute `"workflow_hint": workflow or ""`
  au state d'entrée (canal dédié, pas de pollution de `messages`).
- `_config_for` inchangé (le hint est dans le state, pas la config).

### 1d. State — `backend/app/graph/state.py`

Ajouter le canal `workflow_hint: str = ""` à `MainState` (input-only,
consommé par `WORKFLOW_ROUTER`).

### 1e. Routeur — `backend/app/graph/nodes/workflow_router.py`

`decide_workflow` consomme le hint **en priorité** (avant les marqueurs
textuels), uniquement s'il est dans `KNOWN_WORKFLOWS`. Sinon : log
`WORKFLOW_HINT_IGNORED` + retombe sur la matrice existante (jamais silencieux).

Ordre de priorité :
1. `activity` si activité en cours (continuation §16 — priorité absolue)
2. hint explicite du composer (s'il est valide)
3. `_intent_solve_problem` (marqueurs déterministes)
4. `main`

---

## 2. Nodes des subgraphs orphelins

Suivre le pattern `problem.py` : lazy-init du subgraph compilé en cache
module, invocation, extraction de `workflow_result`, fallback partiel
si vide, log d'observabilité, retour sur `context`.

### 2a. `backend/app/graph/nodes/research.py`

`research_node` → `compile_research_subgraph().invoke(build_initial_state(...))`.
Entrée : `intake.query`, `user_id`, `thread_id`, payload objectives
(deep/academic/news selon la mention). Sortie : `ResearchResult` (§8).

### 2b. `backend/app/graph/nodes/coding.py`

`coding_node` → `run_coding_workflow(...)` (async). Le node est `async def`
(LangGraph supporte les nodes async ; le runner `.ainvoke` déjà utilisé).
Sortie : `CodingResult` (§8). Note : `run_coding_workflow` renvoie un
`CodingResult` **local** à `coding/graph.py` (champs différents du contrat
§8) → adapter dans le node vers le contrat `contracts.CodingResult`.

### 2c. `backend/app/graph/nodes/video.py`

`video_node` → `run_video_subgraph(payload, ...)`. Le payload vidéo
(filename/source_url) vient des attachments/upload, pas du texte —
en l'absence d'attachement, `status="partial"` documenté. Sortie :
`VideoResult` (§8).

### 2d. `WIRED_WORKFLOWS` — terminer

```python
WIRED_WORKFLOWS = {
    "main": "context",
    "activity": "activity",
    "problem": "problem",
    "research": "research",
    "coding": "coding",
    "video": "video",
    "document": "document",
}
```

+ node `document` minimal (délègue à l'API documents existante via
  `workflow_result` générique — contrat `SubgraphResult`, §8 prévoit
  explicitement ce cas).

---

## 3. Câblage dans `compile_main_graph` — `backend/app/graph/main.py`

```python
graph.add_node("research", research_node)
graph.add_node("coding", coding_node)
graph.add_node("video", video_node)
graph.add_node("document", document_node)

# étendre le mapping du conditionnel workflow_router
{"context": ..., "activity": ..., "problem": ...,
 "research": "research", "coding": "coding",
 "video": "video", "document": "document"}

# chaque subgraph rejoint la chaîne principale (pattern problem)
graph.add_edge("research", "context")
graph.add_edge("coding", "context")
graph.add_edge("video", "context")
graph.add_edge("document", "context")
```

La capability gate (§4) existante s'applique alors naturellement à
coding/research/video via `_capability_gate_reason` — déjà implémentée.

---

## 4. Couche MCP (doc §39–§41)

```
backend/app/mcp/
├── __init__.py
├── registry.py      # §39 : registry serveurs (capabilities, permissions, allowed workflows)
├── toolset.py       # §40 : loading + scoping des tools par workflow
└── servers/
    └── calendar.py  # serveur MCP calendar (agenda) — FastMCP stdio
```

### 4a. `registry.py` (§39)

Registry statique validé par pydantic, lu depuis la config/env :

```python
class McpServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = []
    transport: Literal["stdio"] = "stdio"
    enabled: bool = True
    capabilities: list[str] = []      # ex: ["calendar"]
    allowed_workflows: list[str] = [] # §40 scoping
    timeout_s: float = 30.0           # §41 timeouts
    rate_limit: int | None = None     # §41 rate limits
```

### 4b. `toolset.py` (§40/§41)

`get_mcp_tools(workflow)` : `MultiServerMCPClient` sur les serveurs dont
`allowed_workflows` contient le workflow → `load_mcp_tools` → tools
LangChain. Échec d'un serveur = isolation (§41 failure isolation) : log +
continue sans ses tools, jamais de crash du run.

### 4c. `servers/calendar.py`

Serveur MCP `agenda` (FastMCP, stdio) : `check_availability`,
`create_event`, `list_events`. Implémentation in-memory persistée
(JSON sous `data/mcp/calendar.json`) — auth/svg-cal laissée de côté
(volontairement, cf. limites).

### 4d. Intégration agent

Les tools MCP ne sont exposés **qu'au workflow concerné** (§40) : le node
`coding`/`research` résout `get_mcp_tools(<workflow>)` et les passe au
subgraph. Le Main Agent n'en reçoit aucun (§40 explicit).

---

## 5. Composer — `@mentions` → termes → workflow

**Problème** : `useComposerMentions` déclare des mentions mais
`onInserted` ne fait rien de fonctionnel (popover sans handlers).

### 5a. `frontend/src/hooks/use-composer-mentions.ts`

Réécrit : expose `parseComposerTerms(text)` qui extrait les termes
`@deep-research`, `@academic-search`, `@news-search`, `@video`, `@code`,
`@agenda`, `@exercise` du texte et renvoie
`{ workflow: string, query: string }` (terme retiré de la requête).

Mapping termes → workflow backend :
- `deep-research`, `academic-search`, `news-search` → `research`
- `video` → `video`
- `code` → `coding`
- `agenda` → `document` (MCP calendar, §40)
- `exercise` → `activity`

### 5b. `frontend/src/assistant-ui/store.ts`

`sendMessage` parse les termes via `parseComposerTerms` avant l'envoi,
passe `workflow` à `streamChat`.

### 5c. `frontend/src/assistant-ui/api.ts`

`streamChat(userId, threadId, message, model, workflow, ...)` :
- GET stream : `params.set("workflow", workflow)` si présent
- fallback POST : `body.workflow`

---

## 6. Validation

- Compilation du graphe : `compile_main_graph` import + `graph.compile()`
  sans erreur (tous les nodes résolus).
- Importabilité de chaque nouveau node.
- `decide_workflow` : hint valide → workflow ; hint invalide → ignoré + log.
- Tests existants : `test_phase1_graph_contracts.py`, `test_coding_subgraph.py`,
  `test_research_subgraph.py`, `test_video_subgraph.py` (ne doivent pas
  régresser ; certains peuvent nécessiter AUTH_MODE=dev).
- Compilation frontend : `npm run build` (ou `tsc --noEmit`).

---

## Limites assumées

- `video` : sans attachement, le subgraph ne peut pas ingérer — résultat
  `partial` documenté, pas d'ingestion bidon.
- `coding` : le subgraph existant a un contrat de sortie non conforme au
  §8 (classe `CodingResult` locale) — adapté dans le node, pas réécrit.
- MCP calendar : stockage JSON local, pas d'OAuth Google réelle.
- Pas de nouveau système de test : on valide la compilation + les tests
  existants.
