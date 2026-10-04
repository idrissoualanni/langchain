# AGENTS.md — Règles de travail du projet agent-tutor

Ces règles s'appliquent à tout agent et à toute intervention humaine sur ce dépôt.
Elles sont **opposables** : une étape qui les enfreint n'est pas terminée, même si elle
« fonctionne ».

---

## 1. Aucun déploiement en production sans passage staging vérifié

**Règle.** Aucun changement n'atteint la production sans avoir été déployé et vérifié
sur staging d'abord. Le staging n'est pas une option : c'est le filtre.

### Ce qu'est staging

| | Service | Identifiant |
|---|---|---|
| API Render | `agent-tutor-api-staging` | `srv-db0ip2ugekts739sr36g` |
| Frontend Vercel | projet `frontend-staging` | `prj_4SXUwA65qm01U04QZzY62k9rOOUh` |

Staging partage **volontairement le projet Neon de la production** : une frontière de
projet Neon est une frontière d'identité. Un projet séparé, c'est un JWKS séparé, donc
le bug d'audience ne se reproduirait pas. L'isolation des données est assurée par un
rôle PostgreSQL dédié (`staging_owner`, `search_path=staging, public, extensions`), pas
par un projet séparé.

### Séquence obligatoire

1. `git push` — forme basse mémoire, voir §3.
2. `render deploys create <id_staging> --confirm` puis attendre le statut `live`.
3. **Vérifier staging** avec les sondes de §2. Un statut `live` ne suffit pas : le
   service peut démarrer puis échouer. Lire les logs si la sonde ne répond pas.
4. Seulement si §2 est entièrement vert : déployer la production.
5. Rejouer §2 sur la production et comparer.

### Ce qui a justifié cette règle

Le premier déploiement staging a échoué et révélé un bug que la production ne pouvait
pas montrer : `videos` et `video_segments` étaient définies par deux modules
(`connections.py` périmé et `schema.py`), `connections.py` s'exécutant en premier.
Sur une base neuve il créait la mauvaise forme de table, `schema.py` ne faisait plus
rien, et le démarrage mourait sur la création de l'index HNSW `embedding`. En
production le bug était invisible depuis toujours : la table existait déjà dans la
bonne forme, les deux `IF NOT EXISTS` étaient inopérants.

**Ce qui aurait été nécessaire pour que la production tombe :** un déploiement sur une
base neuve — nouvelle région, restauration, nouvel environnement. Rien de spectaculaire,
et c'est ce qui est arrivé.

---

## 2. Vérification : on ne déclare rien sans preuve

Un déploiement n'est « réussi » que si une sonde l'a constaté après coup. On ne
déduit jamais d'un statut, d'un build vert ou d'un exit code.

### Sondes minimales, par environnement

| Sonde | Attendu |
|---|---|
| `GET /api/health` | 200, et `ollama`, `langgraph`, `database` **tous** `true` |
| Statut du deploy | `live`, et le commit déployé **est** le commit poussé |
| CORS avec l'：`Origin` de l'environnement | ACAO = origine exacte, `ACAC: true`, **jamais `*`** |
| Préflight `OPTIONS` sur une route mutante | 200, ACAO présent |
| `POST /api/auth/session` malformé | 401, message **générique**, ACAO toujours présent |
| BASE Neon | schéma attendu présent, tables saines, prod intacte |

### Règles de preuve

- Distinguer **vérifié** de **supposé**. Écrire « je n'ai pas pu vérifier » quand c'est
  le cas, plutôt que de combler le trou par une déduction.
- Une hypothèse ne devient un fait qu'après une expérience qui la tranche. Écrire
  l'hypothèse, puis la tester.
- Un échec d'inférence doit arrêter la tâche, pas être contourné.
- Après correction : **relire la preuve** —返回值 attendue, pas seulement l'absence
  d'erreur.

---

## 3 Mémoire et disque : nettoyer avant les opérations lourdes

La machine fait 16 Go de RAM avec 4 Go de pagination. Les incidents observés —
`WinError 1455` pendant les tests, `malloc failed` sur un `git push`, `ENOSPC` sur une
mise à jour de CLI, et un shell incapable de forker — ont **tous la même cause** : pas
de marge.

### Nettoyage avant `git push`, une mise à jour de CLI, ou une suite de tests

```bash
# 1. mémoire + pagination disponibles
python -c "import ctypes;class_=None" 2>/dev/null   # (voir §3.2 pour la sonde)

# 2. push en consommation bornée — la compression delta sur N threads est
#    précisément ce qui part en allocation abusive sur cette machine
git -c pack.threads=1 -c pack.deltaCacheSize=4m \
    -c pack.windowMemory=16m -c core.packedGitWindowSize=32m push origin master

# 3. caches régénérables, tous déjà ignorés par git
rm -rf frontend/node_modules/.vite frontend/dist frontend/playwright-report
rm -rf frontend/test-results backend/.pytest_cache
find backend agent -name __pycache__ -type d -prune -exec rm -rf {} +   # si_rm le permet

# 4. si le disque est bas (npm/pnpm/git échouent en ENOSPC)
npm cache clean --force && pnpm store prune
```

### Règles

- **Supprimer un cache ne répare pas une RAM saturée.** Mesurer avant de conclure :
  `GlobalMemoryStatusEx` pour la RAM, `Get-PSDrive` pour le disque.
- Ne pas agrandir le fichier d'échange si le disque est presque plein : ça transforme un
  incident mémoire en incident disque, et le second bloque tout.
- `node_modules` n'est pas un cache : sa suppression impose une réinstallation.
- Un nettoyage qui rend le dépôt `git status` sale est un mauvais nettoyage.

---

## 4. Secrets : jamais affichés, jamais journalisés, jamais committés

### Règles

- Un secret ne quitte jamais sa source. Aucun `echo`, `print`, ni journalisation de
  valeur de variable d'environnement, même « juste pour vérifier ».
- Pour inventorier un environnement, **lister les noms**. Pour une valeur précise,
  une liste blanche explicite — et only pour les variables prouvées non sensibles
  (URL d'origines, drapeaux).
- Un secret déjà preprint dans une sortie est **considéré comme divulgué** : le
  faire tourner, ne pas le recopier.
- Les fichiers de travail qui contiennent des secrets vivent hors du dépôt et sont
  supprimés une fois l'opération terminée.
- Ne jamais commiter `.env`, `.env.local`, `.vercel/`.

### Piège connu de l'API Render

`GET /v1/services/<id>/env-vars` :

- `limit` max **100** ; au-delà, HTTP 400.
- la réponse est une **liste** d'objets `{envVar: {...}, cursor}` avec curseur — pas un
  dictionnaire.

Un parsing naïf renvoie **silencieusement zéro variable** au lieu d'échouer. Toute
sonde d'inventaire doit donc **lever une exception si le décompte est nul**, et
n'afficher que les noms par défaut. C'est le seul garde-fou contre la fuite.

---

## 5. Fichiers intouchables

Ne pas modifier sans demande explicite et justification :

```
backend/app/config.py
backend/app/models.yaml
backend/app/services/models/**
backend/providers.yaml
backend/requirements.txt
backend/app/api/health.py
backend/tests/test_model_gateway_wiring.py
backend/app/services/agent/prompts.py
backend/app/graph/nodes/agenda.py
backend/app/graph/subgraphs/video/agent.py
```

**Exception tracée (2026-10-04).** `backend/requirements.txt` a été édité sur **demande
explicite** (« met a jour le requirement ») pour ajouter `mammoth` (conversion Word
`.docx` → Markdown du pipeline d'ingestion knowledge, `services/knowledge/convert.py`).
Toute autre ajout/retrait de dépendance reste soumis à la règle.

---

## 6. Retour arrière

Toute action en production a un retour arrière **défini et testé avant** d'être
appliquée. Sans cela, on n'applique pas.

Un retour arrière n'est pas un réflexe : c'est une décision. **Vérifier l'état réel
avant de « restaurer »** — un rollback exécuté sur un système sain supprime des
correctifs et crée un second incident. En septembre 2026, la production était saine
et fonctionnelle, et le rollback demandé aurait retiré le correctif d'audience qui
débloquait la connexion.

Marquer explicitement le commit connu comme bon (`e83a4d5`, Authentification) pour
que le retour arrière soit une commande, pas une réflexion.

---

## 7. Journal de configuration : le dépôt doit décrire ce qui est déployé

Six variables sont posées en production sans qu'aucun module ne les lise
(`APP_ENV`, `API_CORS_ORIGINS`, `MEMORY_STORE_DB`, `DOCUMENT_STORE_DB`,
`LANGGRAPH_STORE_DB`, `LANGGRAPH_CHECKPOINT_DB`). Elles donnent l'illusion d'un réglage
qui n'existe pas.

**Règle** : une variable d'environnement posée doit être lue par le code, ou sa
présence doit être justifiée dans `ENV.md`.

⚠️ **Un scan statique ne peut pas le prouver.** `TAVILY_API_KEY` a zéro référence dans
le dépôt et fonctionne, parce que le SDK la lit. Pour établir quelles variables sont
réellement consommées, il faut un **suivi d'exécution** de `os.environ` — pas un grep.

---

## 8. Base de connaissance : source, gating, auteur, migrations additives

La base de connaissance de cours obéit à des règles **opposables**.

### 8.1 Source de vérité

- La source de vérité est **Neon** : `knowledge_sections` (corpus vectorisé),
  `knowledge_files` (bucket des pages sources), `subject_definitions` (matières).
  **Aucun dossier Markdown d'exécution** n'est lu au runtime — la mission « aucune
  base de connaissance codée en dur dans le projet » reste en vigueur.
- Le format d'**import** est une page Markdown à **en-tête YAML** (frontmatter :
  `subject`, `topic`, `title`, `author`, `source`), validée par le schéma Pydantic
  `ChunkFrontmatter`. Les définitions de matières sont validées par `SubjectDefinitionIn`.
- Pipeline d'ingestion : PDF/Word → Markdown (`convert.py`), découpage par titres
  avec **secours 800 caractères / chevauchement 100** (`chunk_markdown`), embedding,
  upsert. Recherche **hybride** : `tsvector` (index **GIN**) + cosinus (index **HNSW**).

### 8.2 Gating de validation (fail-closed)

- Une matière porte un **statut** : `draft` / `review` / `validated` / `archived`
  (défaut `draft`). **Seul `validated` rend la matière visible de l'agent** — ni
  routing, ni tools, ni corpus. Le gating est appliqué par le registry
  (`load_subject_definitions(only_validated=True)`), avec un garde-fou redondant
  dans `knowledge_retriever.search_knowledge`.
- L'admin voit **tout** le catalogue (`only_validated=False`) et change le statut via
  `PATCH /api/admin/subjects/{id}/status`.

### 8.3 Auteur (métadonnée obligatoire)

- Toute source et tout chunk porte un **`auteur`** : colonnes `subject_definitions.author`
  et `knowledge_sections.author`. Les défauts vides sont tolérés mais l'auteur doit être
  renseigné à l'import (frontmatter ou paramètre `author`).

### 8.4 Migrations additives et réconciliation

- ⚠️ **Le Neon de staging PARTAGE le projet de la prod.** Toute migration est
  **additive et idempotente** (`ADD COLUMN IF NOT EXISTS`, index `IF NOT EXISTS`) et
  **jamais destructive**. Aucune colonne/table n'est renommée ni supprimée.
- **Grandfathering du statut.** L'ajout de `status` **ne doit pas** gater les matières
  existantes : la migration ajoute la colonne NULLABLE, passe l'existant à `validated`,
  PUIS pose le défaut `draft` (+ `NOT NULL`). Le seed autoritaire
  (`scripts/migrate_knowledge_neon.py`) écrit `validated` à la création et ne touche
  JAMAIS un statut déjà décidé par l'admin sur un ré-import.
- La **réconciliation** (`reconcile_subject_sources`) est la SEULE opération
  destructive : elle est **scopée à un sujet** et déclenchée explicitement
  (`POST /api/admin/knowledge/corpus/reconcile`). Un ensemble vide purge le sujet.
- Les tests d'intégration DB (`backend/tests/test_knowledge_db.py`) sont **opt-in**
  (`DATABASE_URL` + `KNOWLEDGE_DB_TESTS=1`) et purgent un `subject_id` unique en
  teardown — jamais la donnée existante.

### 8.5 Voie d'accès du LLM au corpus

- La voie **par défaut** reste l'injection automatique du context builder
  (`knowledge_retriever`).
- Le tool **`search_knowledge`** (famille `knowledge`) est la voie **explicite et
  auditée** du modèle vers le corpus ; il ne sert que les matières validées.
### 8.6 Reranking (second etage de tri)

- Toute recherche corpus suit deux etages : **generation** (hybride cosine HNSW +
  lexical tsvector, `store.search_hybrid`) puis **reranking**
  (`backend/app/services/knowledge/rerank.py`).
- Le reranker est **interchangeable** (`Reranker` Protocol + `get_reranker` /
  `set_reranker`) : defaut = heuristique locale deterministe (signaux couverture,
  titre, phrase). Un reranker LLM / cross-encoder se branche sans toucher au
  retriever ni au tool.
- Le pool de candidats est genere **plus large** que le `top_k` demande : le
  reranking a besoin de marge pour re-classer (`limit * 4`).
- `normalize_query` est importe **paresseusement** dans rerank.py : l importer au
  niveau module creerait un cycle (rerank -> context.__init__ -> builder ->
  knowledge_retriever -> rerank).

### 8.7 Propositions de connaissance (approbation admin)

- Le tool **`propose_knowledge`** (famille `knowledge`) permet a l agent de
  soumettre un complement de cours. La proposition est ecrite dans
  `knowledge_proposals` avec `status = 'pending'`.
- **Une proposition n entre JAMAIS dans le corpus sans decision admin** : ni la
  recherche, ni les outils, ni le retrieval ne la voient.
- L admin decide via `POST /api/admin/knowledge/proposals/{id}/decide` :
  - `approve=true` -> vectorisation + upsert dans `knowledge_sections`, puis
    `status = 'approved'` ;
  - `approve=false` -> `status = 'rejected'`, rien n entre au corpus.
- Si l embedding echoue a l approbation, la proposition **reste `pending`** ( HTTP
  503 ) : on n arbitre jamais une proposition qui n a pas pu etre indexee.
- Les tests sont offline (`tests/test_knowledge_rerank.py`,
  `tests/test_knowledge_proposal.py`) : store monkeypatche, aucune base requise.