# RAPPORT MISSION V11 — DOCUMENTS UTILISATEUR COMME SOURCE & SCRAPING WEB

Date : 2026-09-19
Périmètre : backend/ + frontend (typecheck) — mission finale, sans commit ni push.

---

## A. Constat de départ (audit)

Deux ruptures fonctionnelles identifiées et cartographiées (`docs/architecture/current-agent-graph.mmd`) :

1. **Documents utilisateur (V10 RAG) n'atteignaient jamais les tools pédagogiques.**
   - Les documents étaient indexés, récupérés (`DocumentRetriever`) et injectés dans le prompt
     (`BuiltContext.user_documents`), mais les outils pédagogiques
     (`create_exercise`, `evaluate_answer`, `give_hint`, `create_quiz`,
     `assess_understanding`) ne recevaient AUCUN canal documentaire : ils se reposaient
     exclusivement sur `_find_section()` (knowledge Registry) et sur du matching
     par mots-clés, sans la référence du document de l'utilisateur.
   - Le tool `search_documents` tronquait le contenu à 500 caractères et n'exposait ni
     `doc_id` ni `chunk_id` exploitables.

2. **Recherche web sans scraping.**
   - `web_search` appelait `ollama.web_search` (snippets courts, bornés par le provider),
     les classait (`rank_web_results`) et les passait directement au prompt.
   - Aucun téléchargement/extraction du contenu réel des pages : un résultat pertinent
     mais peu renseigné par le snippet était donc traité au mieux de l'information
     disponible, au pire ignoré.
   - Aucun événement `SCRAPE_*` et échec partiel d'un URL non géré (tout ou rien).

## B. Changements de comportement

### Partie A — Documents utilisateur comme source pédagogique

`backend/app/agent/pedagogical_tools.py` :

- Nouvelle constante `MAX_DOC_REFERENCE_CHARS = 4000` et marqueur
  `SOURCE_USER_DOCUMENT = "user_document"`.
- Nouveau helper `_reference_section(subject, topic, activity, document_context)` :
  résolution de la référence dans l'ordre `document_context` (argument) →
  activité en cours (`activity["reference"]`) → section knowledge (`_find_section`).
- Nouveau helper `_split_document_blocks(content, num)` : découpe le document en blocs
  de taille équivalente pour générer des questions quiz réparties sur l'ensemble.
- Les 5 tools pédagogiques acceptent `document_context: str | None` ; `evaluate_answer`
  ajoute `document_only: bool = False`.
- `create_exercise` et `create_quiz` stockent dans l'activité :
  - `reference` : contenu documentaire retenu (tronqué à `MAX_DOC_REFERENCE_CHARS`),
  - `source_type` : `"user_document"` quand la référence vient d'un document — la
    provenance du document est conservée à travers l'état de l'activité.
- `evaluate_answer` en mode `document_only=True` retourne un ToolMessage
  `insufficient_reference` (statut explicite) si aucune référence exploitable
  (< 80 caractères) n'est disponible — jamais de réponse inventée. Événement
  `DOC_EVAL_INSUFFICIENT_REFERENCE` émis.
- `create_quiz` : lorsque la source est un document (`source_type == "user_document"`),
  `_build_quiz_questions` découpe le contenu en blocs et génère les questions
  UNIQUEMENT depuis le document (aucun mélange avec la connaissance du Registry).

`backend/app/agent/document_tools.py` :

- `search_documents` : le contenu n'est plus tronqué à 500 caractères (les chunks sont
  déjà bornés par le chunker) ; expose `doc_id`, `chunk_id`, la pertinence (float) et le
  contenu complet par résultat.
- `list_documents` : expose `doc_id` en plus du nom de fichier.

`backend/app/agent/middleware.py` :

- Nouvel ensemble `DOCUMENT_TOOL_NAMES = {"upload_document", "search_documents",
  "list_documents", "delete_document"}` ; le forçage du `user_id` (Runtime Context)
  couvre désormais ces tools en plus des tools mémoire/learning — pas de retournement
  cross-user possible au niveau du middleware.

### Partie B — Scraping web (chaîne Search → Scrape → Extract → Clean)

Nouveau module `backend/app/context/web_scraper.py` :

- `fetch_page_content(url, user_id, thread_id)` : `requests.get` (timeout 8 s, User-Agent),
  vérification `Content-Type` HTML et status 200, extraction du texte éditorial via
  BeautifulSoup (retrait de `script/style/nav/header/footer/aside/form/iframe/...`),
  borne `MAX_SCRAPE_CHARS = 6000`, seuil minimal de contenu (80 caractères).
- Échec **contrôlé et partiel** : timeout, SSL, HTTP ≠ 200, contenu non-HTML, page vide,
  exception inattendue → retourne `("unchanged", None)` — jamais d'exception propagée.
- Événements `SCRAPE_START`, `SCRAPE_END`, `SCRAPE_ERROR`, `SCRAPE_SKIP`.
- `scrape_results_snapshot(results, max_scrape, ...)` : enrichit par copie les objets
  `SearchResult` retenus (champs `content`/`snippet` remplacés par le contenu extrait,
  `metadata["scraped"]="yes"`), une URL bloquée n'empêche pas le scraping des autres.

`backend/app/context/web_search.py` :

- Branch après `rank_web_results` : pour les résultats retenus (≤ `top_k`), appel de
  `scrape_results_snapshot`. Si une page est injoignable, le snippet provider est
  conservé (échec partiel supporté). Le statut `found/insufficient` reste inchangé.

`backend/app/logging/events.py` (convention) : événements `SCRAPE_*` et
`DOC_EVAL_INSUFFICIENT_REFERENCE` utilisés.

### Partie C — Priorité `user_documents` quand la requête cible un document

`backend/app/context/builder.py` :

- Nouveau helper `_query_targets_document(query)` (marqueurs lexicaux : « mon document »,
  « mes cours », « ce pdf », « mes notes », … — simple, rapide, zéro NLP).
- Détection lors du retrieval V10 : si la requête cible un document,
  - `top_k=6` (au lieu de 4) pour le retrieval documents,
  - événement `DOCUMENT_TARGET_DETECTED`,
  - priorité de la section `user_documents` : **P1** (jamais droppée, §43) au lieu de P2
    — le contenu du document devient une source prioritaire dans le budget de contexte.
- Sans cible explicite, comportement inchangé (P2).

### Partie D — Tests

`backend/tests/test_v11_document_web.py` — pattern identique à `test_v52_unit.py`
(ScriptedModel via `create_agent`, MemorySaver, middleware réel) :

- §43 exercice depuis un document → `source_type=user_document`, référence stockée.
- §44 évaluation sur référence documentaire (score, attempts, status).
- §50 deux références différentes (membrane vs endocytose) → scores DIFFÉRENTS,
  prouvant que le contenu du document est réellement lu (pas de matching figé).
- §52 `document_only` sans référence → `insufficient_reference`, aucune évaluation
  fabriquée.
- §47 quiz depuis un document (mode document, stockage référence + source_type).
- §51 middleware : `DOCUMENT_TOOL_NAMES` couvre les 4 tools documents.
- §53 search → scrape : `web_search` déclenche le scraper, contenu enrichi.
- §54 scraping fail-safe : HTML propre, timeout → unchanged, PDF → unchanged,
  403 → unchanged, échec partiel multi-URL → 1 scrapée + 1 conservée.
- §55 détection cible documentaire (6 cas).
- §56 provenance document → tool : référence complète conservée et bornée.

## C. Décisions techniques (justification §3 « ne pas refaire »)

- **Aucun nouveau framework** : scraping via `requests` (déjà présent) + `BeautifulSoup`
  (déjà présent). Aucun nouveau provider, vector store, architecture RAG, multi-agent.
- **Aucune rupture des contrats existants** : `SearchResult`/`SearchResponse`/
  `BuiltContext` inchangés (les champs ajoutés sont des clés `metadata` — un dict libre).
  `SearchResult` reste mutable par copie, la pertinence déjà calculée n'est pas modifiée.
- **Le contenu brut du document est transporté dans l'état de l'activité**
  (`activity["reference"]` tronqué à 4000) et fourni à chaque tool au moment de
  l'évaluation : c'est la rupture centrale R4 qui est adressée, conformément aux
  principes §6/§20/§52.
- Le LLM contrôle `query` ; jamais de `user_id` injecté dans le prompt — le middleware
  force `user_id` côté Runtime Context pour l'isolation (§9/§15).

## D. Tests — résultats (§72 : PASS / FAIL / BLOCKED)

| Test | Résultat | Détail |
|---|---|---|
| `test_v11_document_web.py` (V11, 31 checks) | **PASS** | §43→§56, 31/31, 0 FAIL |
| `test_v52_unit.py` (V5.2 pédagogique, 73 checks) | **PASS** | 73/73 hors test API environnemental (voir ci-dessous) |
| `test_v10_context_documents.py` | **PASS** | 16/16 — non-régression V10 (priorité P1, top_k=6) |
| `test_v68_context_budget.py` | **PASS** | 17/17 — non-régression budget (P1 jamais droppée) |
| Frontend `npx tsc -b` | **PASS** | exit 0, aucune erreur de type |

Tests attestés BLOCKED (blocages environnementaux documentés, INDÉPENDANTS de V11) :

| Test | État | Blocage |
|---|---|---|
| `test_v52_unit.py` §51 (cross-user API) | **BLOCKED** | `POST /api/users` → **405** : AUTH_MODE=clerk, le provisioning dev-user est inaccessible hors serveur configuré |
| `test_v65_search.py` | **BLOCKED** | requiert serveur :8001 (API externe) |
| Exécution web réelle (`ollama.web_search`) | **BLOCKED** | dépend de la clé OLLAMA_API_KEY + fournisseur externe — les tests V11 couvrent le branch par mock |

## E. Vérification des points §72/§73 (mission)

- [x] Chaque test est marqué PASS / FAIL / BLOCKED ci-dessus.
- [x] Aucune erreur de type frontend (`npx tsc -b`, exit 0).
- [x] Aucun commit, aucun push, aucun changement du core architecture non requis.
- [x] Les tests pédagogiques V5.2 et les suites V10/V6.8 passent (aucune régression).

## F. Points d'attention / limites

- La détection de cible documentaire (Partie C) est volontairement **lexicale** (listes
  de marqueurs). Elle n'augmente que la priorité/le budget : jamais de faux retrait —
  en cas de doute, le comportement P2 par défaut est conservé.
- Le scraping est **relationnel à une latence réseau** : timeout 8 s par URL, borné au
  nombre de résultats retenus (≤ top_k). En cas de site lent, le snippet provider sert
  de secours (échec partiel, §32).
- `activity["reference"]` est borné à 4000 caractères : un document très long perd sa
  queue — c'est un budget volontaire (le chunker V10 borne déjà à la source).
- Espace disque limité à l'époque de la mission (fichier restauré via `git checkout`
  suite à une écriture entravée par le disque plein) : la partition C disposait de ~1 Go
  libre après nettoyage ; aucune nouvelle dépendance installée.

## G. Fichiers modifiés / créés

**Modifiés :**
- `backend/app/agent/pedagogical_tools.py` — canal documentaire (Partie A).
- `backend/app/agent/document_tools.py` — contenu complet + provenance (Partie A).
- `backend/app/agent/middleware.py` — `DOCUMENT_TOOL_NAMES` (Partie A).
- `backend/app/context/web_search.py` — branch scraping (Partie B).
- `backend/app/context/builder.py` — priorité dynamique `user_documents` (Partie C).

**Créés :**
- `backend/app/context/web_scraper.py` — scraping fail-safe (Partie B).
- `backend/tests/test_v11_document_web.py` — suite de tests V11 (Partie D).
- `docs/architecture/current-agent-graph.mmd` — cartographie.

**Non modifiés (aucune reprise) :** `app/rag/`, `app/context/schemas.py`,
`prompt_builder`, `app/api/*`, `frontend/src/*` (typecheck seul), learning engine.

## H. Workflow de vérification

```
cd backend
PYTHONIOENCODING=utf-8 python tests/test_v11_document_web.py    # 31/31
PYTHONIOENCODING=utf-8 python tests/test_v52_unit.py            # 73/73 (hors API BLOCKED)
PYTHONIOENCODING=utf-8 python tests/test_v10_context_documents.py  # 16/16
PYTHONIOENCODING=utf-8 python tests/test_v68_context_budget.py  # 17/17
cd ../frontend && npx tsc -b
```

## I. Historique

- 2026-09-19 — V11 Documents & Web : implémentation A+B+C, suite de tests D
  (31/31), non-régression V10/V6.8/V5.2, typecheck frontend.

## J. Signatures

- Rédigé dans le cadre de la mission finale V11 — « Documents utilisateur comme source
  & Recherche web avec scraping ».
- Aucun commit / push effectué (conforme à la mission).