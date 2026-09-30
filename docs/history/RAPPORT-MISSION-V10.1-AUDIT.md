# RAPPORT — MISSION V10.1 : STABILISATION POST-V10 (ÉTAPE AUDIT)

Date : 2026-09-17/18 · Branches concernées : `master` (HEAD `04ac164`) · État : **audit en cours, aucune modification de code effectuée dans cette étape**.

---

## 1. Cadre de la mission

Périmètre strictement **post-V10** (aucun refaire de V10, aucun V11 Advanced Retrieval, aucune nouvelle brique externe). Règles :
- Interdits : Qdrant (+reranker externe), nouveau provider LLM, Multi-Agent, MCP, Guardrails V8, Langfuse / OpenTelemetry complet, nouveau système mémoire/documents, réécriture de l'architecture existante.
- Documentation : identifier les versions installées → consulter la documentation officielle correspondante → ne pas copier d'exemples d'anciennes versions → références documentées dans le rapport.
- Ne **jamais supprimer ni désactiver** un test existant.
- La mission doit se terminer sur la branche principale = **`master`**.

## 2. Baseline git

- Branch HEAD : `master` `04ac164` « MISSION V7.1-V8 : Identite Clerk + Frontend Assistant UI ».
- `audit-cleanup` au même commit `04ac164` ; `mission/v5.2-pedagogical-tools` = `f6dbc52`.
- Avancement V10 non commité (pas de freeze fait) ; pollution héritée de l'audit-cleanup (renames stagés, suppres, backups). Le freeze V10 fera l'objet d'une étape dédiée.

## 3. Versions installées (documentation officielle à consulter avant modif)

Backend (`python -X utf8`, pip) :
- fastapi `0.139.0`, langchain `1.3.15`, langchain-core `1.5.5`, langchain-text-splitters `1.1.2`, langchain-ollama `1.1.0`, langgraph `1.2.11`, langsmith `0.11.0`, pydantic `2.12.5`, numpy `2.4.3`, httpx `0.28.1`, pytest `8.3.4`.

Frontend :
- `@assistant-ui/react ^0.15.19`, `react ^19.2.8`, `framer-motion ^13.2.0`, `lucide-react ^1.46.0`, Tailwind (`tailwind` present).

Ollama : **UP** (`/api/tags`) — qwen3-embedding:0.6b, gemma3:4b, qwen2.5:1.5b, etc. Embeddings actifs : `active: ollama-0-6b` (qwen3-embedding:0.6b, dim 1024, timeout 10 s), fallback déterministe `local-hash` dimension 12289.

## 4. Audit RAG (objectif 2/3)

Structure auditée : `backend/app/rag/{chunker,documents,vector_store,retriever,schemas}.py`.

### 4.1 Pipeline vérifié
- Extraction textes : markdown, txt, rst via utf-8/utf-8-sig/latin-1 ; PDF via PyMuPDF (`fitz`) ; erreurs contrôlées (pas de crash), limites de taille.
- Chunking : ~500 tokens, overlap ~50, blocs de code atomiques, bornes sur titres Markdown.
- Embedding vectoriel : Ollama `qwen3-embedding:0.6b` (1024 d) avec fallback `local-hash` ; injection contexte documents (retriever, `MAX_CONTEXT_CHUNKS=4`).
- Indexation : tables `documents` + `chunks` (SQLite) ; suppression document (par doc_id + user_id), recherche par similarité.

### 4.2 Point d'attention — métadonnées de chunk
La mission exige que **chaque chunk conserve au minimum** : `user_id, document_id, subject_id, topic, source_type, filename, chunk_id`.

Constat API :
- `chunks` stocke : `chunk_id, doc_id, user_id, idx, content, emb, dim`.
- Les champs `subject_id`, `topic` ne sont **pas** stockés par chunk (couplage sujet/topic au niveau document uniquement, et non garanti — un document peut couvrir plusieurs sujets).
- `filename` n'est stemé que dans la jointure `documents` (`DocumentRecord.filename`), pas lu dans le contexte chunk retourné.
- `source_type` est déduit (extension enregistrée sur `documents`), pas portée par les chunks.
- **Recommandation V10.1** (minimale, sans réécriture) : ajouter les colonnes `subject_id`, `topic`, `source_type`, `filename` sur `chunks` (valeurs remplies à l'indexation) et enrichir la sortie retriever → les tests `test_context_contracts` / `test_v10_context_documents` couvrent déjà le contrat vide, à étendre sans suppression.

### 4.3 Isolation multi-utilisateur (aperçu)
- `user_id` obligatoire, clés `(doc_id, user_id)` et `WHERE user_id=?` → isolation documentaire présente.
- Vérification ownership sur la suppression (à confirmer ligne par ligne à l'étape sécurité multi-utilisateur).

## 5. Mémoire sémantique (objectif 4)

Audité : `backend/app/agent/memory.py` + `backend/app/context/semantic/*`.
- Profil utilisateur : `NAMESPACE_LABEL = "users/profile"`, champs connus (PROFILE_FIELDS), dédup sur seuil (`DEDUP_THRESHOLD = 0.72`).
- Facts mémoire : catégories déclarées (FACT_CATEGORIES), sources, hybride lexique + vecteur ; écrêtage tokens du contexte.
- Failles constatées : **aucune** critique à ce stade ; tests ciblés non encore exécutés (voir §10 baseline incomplète — `test_context_contracts` couvre mémoire = OK 50/50).
- Provider embeddings : LLM (Ollama) + fallback déterministe local-hash ; erreurs consommées (jamais propagées au pipeline). Conforme fail-safe §15.

## 6. Tools (objectif 4/5/6)

- `all_tools` (tools.py) agrège : tools de base + `memory_tools` + `pedagogical_tools` + `learning_tools` + `code_tools` + `document_tools`.
- `document_tools` : 4 tools (recherche/liste/upload/suppression documents) branchés **dehors** de la Knowledge Base (pas de dépendance pédagogique).
- `pedagogical_tools` : 7 `@tool` ; aucune trace lue de duplication de la Knowledge Base.
- Assistant UI : le composer rejette toujours `application/pdf` (aucune acceptisation pdf dans l'adapter composite) → **à corriger** en suivant la doc officielle `@assistant-ui/react` 0.15, et ce SANS exposé homme/machine ASCII d'exemple périmé.
- **Modèles (sélecteur du composer)** : `GET /api/models` liste désormais les modèles **configurés dans `models.yaml`** (`list_configured_models()` dans `model_capabilities.py`), mappés sur leur nom réel Ollama, avec repli sur les tags Ollama si le YAML est vide. Contrat `BackendModel`/`ModelInfo` inchangé (id, name, description, active). Le YAML actuel ne déclare que `gemma4:31b-cloud` → c'est l'unique choix affiché. (`model_capabilities.py` : `list_configured_models` ; `api/models.py` : `api_list_models` repensée.)

## 7. Activités / AgentResponse (objectif 7)

- `AgentResponse` (pydantic) aligné sur `response.py` ; `activity_state.py` porte les statuts dess (exercise/quiz/understanding_check…) ; le panneau droit frontend s'appuie sur `types/agent.ts` + `types/agentResponse.ts`.
- Concordance vérifiée par `test_v67_output` 30/30 (voir §9).

## 8. Sécurité multi-utilisateur (objectif 9) — PAS ENCORE AUDITÉ EN DÉTAIL

Non réalisée à cette étape (étape prévue séparément). Aucun changement effectué.

---

## 9. Baseline de tests — résultats réels

| Suite | Résultat | Commentaire |
|---|---|---|
| `test_v10_context_documents.py` | **16/16 PASS** (0.9 s) | validation RAG V10 |
| `test_context_contracts.py` | **50/50 PASS** (2 m 31 s) | contrats RAG + mémoire |
| `test_v68_context_budget.py` | **17/17 PASS** (5.4 s) | budget contexte |
| `test_v68_final_integration.py` | **16/16 PASS** (5.7 s) | finalité V6.8 |
| `test_v65_search.py` | **non exécutable** | exige serveur `:8001` (BASE_PORT), suite E2E hors scope direct |
| `test_v66_fallback.py` | **21/22 — 1 ÉCHEC** | test 13 « ambiguous réel → candidates transmises à la décision » |
| `test_v67_output.py` | **30/30 PASS** | sorties/cartes AgentResponse |
| `test_v71_semantic.py` | non exécuté (Ollama réel long) | à prévoir en annexe |

### 9.1 Diagnostique de l'unique échec — test_v66_fallback, test 13

Requête : `build_context("v66-t", "v66-t", "Parle-moi des reseaux.")` ; attendu `fallback.action == "ask_clarification"` + `candidates ⊇ {computer_networks, neural_networks}`.

Résultat réel observé :
- `route_subject("Parle-moi des reseaux.")` → `supported | computer_networks | topic=None | conf=0.85 | candidates=[]` (probe directe, no LLM).
- `route_subject("Explique-moi les reseaux.")` → idem `supported | computer_networks` (alors que `test_v71_semantic` §6a attend `ambiguous {computer_networks, neural_networks}`).
- `route_subject("Parle-moi des reseaux neurones.")` → `ambiguous | ['computer_networks','intelligence_artificielle']` → **ce cas-là reste conforme**.

Cause racine : **l'alias simple « réseaux » ajouté dans `definitions/computer_networks.yaml` (ligne 54, commit `04ac164` V7.1-V8)**. Cet alias (mot simple ≥2.0, `_word_in`) capture « reseaux » nu dans le matcher modèle §13-§14 **avant** la détection taxonomy `unsupported_hits` (§18 « les réseaux » → 2 hits taxonomy). Or l'intention documentée (taxonomy.py:17-18) et les tests référence (§31 V6.5, §6a V7.1) exigent que « reseaux » (sans « neurones ») reste **ambiguous** entre `computer_networks` et `neural_networks` ; seulement « reseaux neurones » se branche sur `intelligence_artificielle`.

La baseline V10.1 est donc **fragile non réglementaire du contract existant** : pas une régression introduite par V10 (le comportement date de V7.1-V8) mais un test V6.6/V6.8 mis en défaut par un choix de config Registry survenu après. **Pour rétablir la sémantique documentée : retirer l'alias simple « réseaux » de `computer_networks.yaml`** (conserver « reseaux informatiques », « computer networks », etc.). Impact prévu :
- « reseaux » nu → 2 hits taxonomy → `ambiguous {computer_networks, neural_networks}` conforme §13/§18, test 13 repasse.
- « reseaux neurones » → reste `ambiguous {computer_networks, intelligence_artificielle}` (le sujet IA matche « neurone(s) » via alias).

À valider par exécution ciblée : `test_v66_fallback`, `test_v5_architecture` (S51), `test_v67_output`, `test_v68_*`, `test_v10_*` → aucune modification autre que ce retrait d'alias, sans supprimer/désactiver de test.

---

## 10. Baseline incomplète (non exécuté à ce jour)

- `test_v5_architecture.py`, `test_v5_integration.py`, `test_v6_integration.py`, `test_v6_learning.py`, `test_v7_learning_engine.py`, `test_v68_models.py`, `test_final_integration.py`, `test_auth_security.py`, `test_clerk_jwt_leeway.py`, `test_v52_unit.py` (peut être bloqué par modure) → à lancer à l'étape Stabilisation pour fabriquer la ligne de base complète.

## 11. Décisions requises avant l'étape procuration

1. **Retrait de l'alias « réseaux »** dans `computer_networks.yaml` afin de rétablir le contrat `ambiguous` de « reseaux » nu (test 13 + §31 + §6a), avec re-exécution complète des suites V6.5→V6.8/V10.
2. **Complétion des métadonnées chunks** (`subject_id`, `topic`, `source_type`, `filename`) — recommandée minimale, sans réécriture ; confirmation nécessaire car implique une migration légère du schéma SQLite + enrichissement retriever.
3. **Freeze V10 sur `master`** : tri de la pile de travail (renames défs, suppressions, fichiers V10) puis commit unique ; à définir si on commit le correctif 9.1 avant ou après le freeze.

## 12. Références documentation officielle (à consulter AVANT toute modification de code)

- LangGraph : `https://python.langchain.com/docs/langgraph/` (version installée 1.2.11).
- LangChain Core / Text Splitters : `https://python.langchain.com/docs/` (1.3.15 / 1.1.2).
- Assistant UI : `https://www.assistant-ui.com/docs/` (0.15.x, React 19).
- PyMuPDF : `https://pymupdf.readthedocs.io/` (extraction PDF existante).
- Pydantic v2 : `https://docs.pydantic.dev/2.12/` (mocked `extra=forbid`).

(Fichier d'étape — sera consolidé dans le RAPPORT final V10.1.)