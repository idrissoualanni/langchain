# MISSION V5.2 — RAPPORT FINAL (intermédiaire)

**Branche** : `mission/v5.2-pedagogical-tools` (créée depuis `master`, jamais fusionnée)
**Statut** : Backend ✅ fonctionnel et testé (55/58 assertions) — Frontend ⬜ non commencé — Commit ⬜ non fait
**Cohabitation** : aucun fichier de l'agent 1 (Learning Profile) modifié dans sa sémantique ; aucun fichier protégé touché.

---

## A. Résumé

Mission V5.2 : transformer le chatbot en **environnement d'apprentissage interactif** via 10
tools pédagogiques (7 améliorés/nouveaux + 3 de pratique du code), un **état d'activité dans le
Thread State** (persisté par le checkpointer, jamais en User Memory, jamais dans Learning
Profile), une **exécution de code sandboxée** en sous-processus isolé (§27 respecté : jamais dans
le process FastAPI principal), des **événements temps réel** (17 nouveaux types) et une **API
d'activité**. Tout est branché **sans toucher** `graph.py`, `runner.py`, `middleware.py`,
`context/builder.py`, `context/router.py`.

Mécanisme clé validé : les tools retournent `Command(update={...})` (langgraph) et lisent l'état
via `InjectedState` — l'écriture d'état se fait donc depuis les tools eux-mêmes, sans modifier le
graphe ni le runner de l'autre agent.

---

## B. Mécanisme d'architecture (zéro fichier protégé modifié)

| Contrainte | Respect |
|---|---|
| Ne pas modifier `graph.py`, `runner.py`, `middleware.py`, `context/builder.py`, `context/router.py` | ✅ aucun modifié (les `M` visibles sur `middleware.py`/`context/*` dans `git status` sont les changements de l'agent 1) |
| État d'activité dans Thread State | ✅ `learning_activity` (dict) + `activity_log` (reducer `operator.add`) + `code_runs` (int) déclarés dans `CustomAgentState` (`state.py`) |
| Écriture d'état depuis les tools | ✅ `Command(update={...})` + `InjectedState` + `InjectedToolCallId` — pattern validé par scratch puis par les tests |
| Persistance inter-redémarrages | ✅ via SqliteSaver existant (test §49 : nouvelle instance d'agent + même checkpointer → activité récupérée, même `activity_id`) |
| `activity_log` accumulé entre runs | ✅ `Annotated[list, operator.add]` (sinon LangGraph écrase) |

Fichiers d'état : `app/agent/state.py` (3 champs ajoutés) + `app/agent/activity_state.py`
(constantes de statuts/types d'activité, `summarize_activity()` qui **ne fuit jamais** les
réponses attendues vers le client).

---

## C. Outils pédagogiques améliorés (compat V4.1 conservée)

Mêmes noms, même logique knowledge-backed (`_find_section`, `_key_terms`, scoring de
couverture) — désormais **interactifs** :

- **`create_exercise(subject, topic)`** — construit l'exercice depuis la vraie section du cours
  (`app/knowledge/**/*.md`), détecte le type de réponse attendu (`_expected_response_type` :
  `code` si la matière déclare `execute_code`, sinon texte), passe l'activité en
  `waiting_for_answer`, instruit le LLM de poser la question PUIS attendre. Topic inconnu →
  liste des topics réels disponibles.
- **`evaluate_answer(subject, topic, answer)`** — scoring 0.7×couverture + 0.3×richesse sur les
  termes clés réels du cours. Score ≥ 0.75 → `checking_understanding` + consigne d'appeler
  `assess_understanding` ; 0.4–0.75 → `waiting_for_retry` ; < 0.4 → `waiting_for_retry` + conseil
  `give_hint`. Incrémente `attempts`, stocke `last_evaluation` (score, verdict, manqués).
- **`give_hint(subject, topic, level)`** — **progressif strictement** : jamais de recul, avance
  de +1 max par appel (demandé ≤ courant → redonne le courant ; demandé > courant →
  `min(courant+1, 2)`). Niveaux 0/1/2 construits depuis le contenu réel du cours. Le saut direct
  0→2 est impossible (test 46c).

## D. Nouveaux outils pédagogiques

- **`create_quiz(subject, topic, num_questions)`** — questions générées depuis les sections
  réelles (topic demandé + voisines), stockées dans `learning_activity.questions`, **une seule
  question posée** (1/N) ; `status=waiting_for_answer`.
- **`create_quiz_next(...)`** — avance l'index après évaluation ; à la fin → `QUIZ_COMPLETED`
  avec score et bilan. (Design §18 minimal : quiz réutilise `learning_activity`, pas de champ
  dédié ; 2 tools au lieu de 3.)
- **`assess_understanding(subject, topic, response)`** — **observation, pas maîtrise** : statut
  `understood / partial / unclear / not_understood` selon couverture + longueur, retourne
  `understood[]`, `unclear[]`, `confidence`, `recommended_action`. **Aucune écriture Learning
  Profile** (test 52 le vérifie structurellement : tools agent 1 intacts).
- **`propose_review(subject)`** — plan de révision depuis les topics réellement disponibles +
  termes manquants et `hint_level` de l'activité en cours.

## E. Outils de pratique du code (sandbox §27)

`app/agent/code_tools.py` — **jamais un "Python Agent"** : activation générique par config de
matière (`_code_tools_enabled` lit `tools.specialized` du YAML ; aucun `if subject == "python"`,
test §38 biologie inclus) :

- **`execute_code(language, code, subject)`** — garde : matière autorisée, python seul, taille
  ≤ 8000, quota ≤ 40 runs/thread (`code_runs`), **scan statique AVANT exécution** (import
  os/sys/socket/subprocess/requests/urllib/http/ctypes/shutil/pathlib, `__import__`, `eval`,
  `exec`, `compile`, `globals`, `locals`, `open`, multi-statement) → **exécution réelle** en
  sous-processus `python -I -B`, env purgé (`_safe_env` : PATH, encodage, no-bytecode, hashseed,
  HOME/TMPDIR=racine sandbox — **aucun secret serveur**, test s9), cwd répertoire jetable dédié
  sous `backend/database/code_runs`, timeout 10 s. Retour réel
  `{status, stdout, stderr, exit_code, duration_ms}`.
- **`run_tests(language, code, tests)`** — construit un harness (code étudiant + un
  `try/except` par test, résultats JSON), l'exécute isolé (15 s), parse et rapporte ✓/✗ par test
  avec obtenu/attendu.
- **`analyze_code(language, code)`** — `compile()` pour la syntaxe **sans exécuter**, règles
  style/logique (print vs return, `except` nu, `while True`, défaut mutable, longueur…), retour
  structuré. **Règle §31 : le LLM ne réécrit JAMAIS le code de l'étudiant sans permission**
  (règles 24–26 du prompt + consignes dans les retours des tools).

Bugs réels trouvés & corrigés pendant les tests : NameError
`ACTIVITY_TYPE_UNDERSTANDING_CHECK` (référence résiduelle) ; WinError 5 sur
`TemporaryDirectory` (TMP système interdit par la sandbox de session → racine déplacée sous
`backend/database/code_runs` avec nettoyage `rmtree(ignore_errors=True)`) ; schéma Pydantic
rejetant `None` quand il n'y a pas d'activité (champs rendus nullables).

## F. Événements temps réel (tous RÉELS, aucun ne vient du frontend)

17 nouveaux types via `log_event` → `agent.log` + SSE `/api/events` :
`ACTIVITY_STARTED`, `ACTIVITY_WAITING`, `ACTIVITY_ANSWER_RECEIVED`, `ACTIVITY_EVALUATED`,
`ACTIVITY_HINT_REQUESTED`, `ACTIVITY_UNDERSTANDING_ASSESSED`, `ACTIVITY_REVIEW_PROPOSED`,
`QUIZ_STARTED`, `QUIZ_QUESTION`, `QUIZ_COMPLETED`, `CODE_EXECUTION_START/END/ERROR`,
`CODE_TEST_START/END/ERROR`, `CODE_ANALYSIS`.

## G. API

`app/api/activity.py` (préfixe `/api/threads`, enregistré dans `main.py`) :

- **`GET /{thread_id}/activity?user_id=`** — vérifie la propriété du thread (403 sinon, test
  51a), lit le snapshot checkpointer, retourne la vue `summarize_activity` (réponses attendues
  et questions non posées **exclues**) + journal d'activité + `interaction_count`.
- **`POST /{thread_id}/run-code`** — exécution directe pour l'éditeur frontend : propriété
  validée (403, test 51c), taille, scan statique (400, test 51e), `run_python_isolated`, renvoie
  `CodeRunResponse`.

Schémas ajoutés à `schemas.py` (après le champ `learning` de l'agent 1, préservé) :
`ActivitySummary`, `ActivityLogEntryOut`, `ThreadActivityResponse`, `CodeRunRequest`,
`CodeRunResponse`.

## H. Prompt & configuration matières

- `prompts.py` — règles **16–26** ajoutées (règle 15 de l'agent 1 préservée verbatim, test 52) :
  activité en cours, une question puis on attend, "Bonjour/Ok" ≠ réponse, clarification, hint
  progressif, vérification de compréhension, quiz conversationnel, multi-tentatives, pratique du
  code sans réécrire le code de l'étudiant.
- YAML matières : `python.yaml` ajoute en commun `create_quiz`/`assess_understanding`/
  `propose_review` et en spécialisé `execute_code`/`run_tests`/`analyze_code` ;
  `biology`, `computer_networks`, `mathematics` n'ajoutent que les 3 outils communs (test s11 :
  biologie n'a PAS execute_code).
- `tools.py` — import additif de `code_tools` et ajout à `all_tools` (24 tools au total), les
  learning tools de l'agent 1 intacts.

## I. Tests — résultats réels

`backend/tests/test_v52_unit.py` (1237 lignes, script autonome, modèle scripté sans Ollama) :
**55 PASS / 3 FAIL** sur les tests critiques §43–§52 + sandbox + §38 :

| Section | Résultat |
|---|---|
| §43 exercice sans réponse (reste en attente, "Bonjour" ≠ réponse) | 7/7 ✅ |
| §44 réponse → évaluation → compréhension | 3/4 (44b : calibrage, voir K) |
| §45/§46 blocage → hint progressif 0→1→2, saut direct interdit | 5/5 ✅ |
| §47 quiz une question à la fois, Q2 invisible, fin → completed | 7/7 ✅ |
| §48 code multi-tentatives + run_tests + analyze_code | 4/5 (48d : vrai bug, voir K) |
| §49 restart (nouvelle instance, même checkpointer) | 2/2 ✅ |
| §50 cross-thread (aucun transfert d'activité) | 3/4 (50c : calibrage, voir K) |
| §51 cross-user API (403 lecture, 403 run-code, 400 réseau, exécution réelle) | 5/5 ✅ |
| Sandbox sécurité (exécution réelle, NameError, timeout, scan réseau/fichiers/eval, secrets absents, quotas matières) | 12/12 ✅ |
| §52 agent 1 intact (4 tools learning + règle 15) | 5/5 ✅ |
| §38 indépendance matières (biologie fonctionne, pas de code) | 2/2 ✅ |

## J. Cohabitation avec l'agent 1 — audit final

- **Mes modifications** : `pedagogical_tools.py` (réécrit), `state.py` (3 champs), `tools.py`
  (additif), `prompts.py` (règles 16–26 après leur règle 15), `schemas.py` (5 classes
  appendues), `main.py` (import + `include_router`), 4 YAML matières.
- **Mes fichiers** : `activity_state.py`, `code_tools.py`, `api/activity.py`,
  `test_v52_unit.py`, `_scratch_agent_pattern.py` (à supprimer).
- **Jamais touchés par moi** : `learning_tools.py`, `app/learning/`, `api/learning.py`,
  `middleware.py`, `context/*`, `api/subjects.py`, tests V6, fichiers frontend learning de
  l'agent 1. Conflits d'édition croisés (schemas.py, prompts.py) résolus par re-lecture +
  ré-application additive.
- Commit prévu : `git add` **explicite** de mes seuls fichiers (jamais `-A`, jamais les fichiers
  learning).

---

## K. CE QU'IL RESTE À FAIRE

1. **Bug réel `run_tests` (le seul)** : le harness généré compare `_actual == 5` (repr str vs
   littéral int) au lieu de comparer les DEUX en repr → 0/3 au lieu de 2/3. Fix : encoder
   `'passed': _actual == repr(expected)` (les deux côtés en chaîne).
2. **Recalibrer 2 tests** : 44b — `assess_understanding` tourne dans le même tour que
   `evaluate_answer` (test compressé) donc l'activité finit `completed` (état final légitime) :
   scinder en deux tours ou accepter `checking_understanding|completed` ; 50c — le topic
   `"loops"` n'existe pas comme section (sections réelles : `for`, `while`, `range`,
   `break-continue`, `comprehensions`) : utiliser `"while"`.
3. **Frontend — non commencé** (l'essentiel du reste) :
   - `types/agent.ts` (**re-lire d'abord : l'agent 1 l'a modifié**) : `ActivitySummary`,
     `ActivityLogEntry`, `CodeRunResult`, + 10 nouveaux `TOOL_NAMES` ;
   - `api/agent.ts` : `getThreadActivity()`, `runCode()` ;
   - `CodeEditor` + bouton **Exécuter** (frappe → POST run-code → résultat réel) ;
   - panneaux `TestResultPanel` / `CodeAnalysisPanel` ;
   - `ActivityFeed` alimenté par les vrais événements `ACTIVITY_*`/`QUIZ_*`/`CODE_*`
     (`useChat.ts` + `ToolStatusPanel.tsx` TRACE_EVENTS) ;
   - build Vite/pnpm + vérification.
4. **Supprimer** `backend/tests/_scratch_agent_pattern.py` (scratch de validation du pattern).
5. **Commit** sur la branche (liste explicite de fichiers, vérifier `git status` avant).
6. Optionnel : tests d'intégration avec LLM réel (Ollama qwen2.5) pour vérifier que le modèle
   suit les règles 16–26 (les tests actuels pilotent les tools directement).

---

## Arborescence réelle du projet (§53)

```
backend/
  app/
    agent/
      activity_state.py      [V5.2 NOUVEAU — états/constantes d'activité]
      code_tools.py          [V5.2 NOUVEAU — execute_code/run_tests/analyze_code + sandbox]
      pedagogical_tools.py   [V5.2 RÉÉCRIT — 7 tools interactifs à Command]
      state.py               [V5.2 MODIFIÉ — learning_activity/activity_log/code_runs]
      tools.py               [V5.2 additif — +code_tools ; V6 additif conservé]
      prompts.py             [V5.2 additif — règles 16–26 ; V6 règle 15 conservée]
      graph.py  runner.py  middleware.py   [INTACTS (middleware modifié par agent 1)]
      learning_tools.py     [AGENT 1 — intact]
    api/
      activity.py            [V5.2 NOUVEAU — GET activity / POST run-code]
      schemas.py             [V5.2 additif — 5 classes après le champ learning V6]
      main.py                [V5.2 additif — include_router(activity)]
      chat.py  context.py  health.py  logs.py  memory.py  subjects.py  threads.py  users.py
      learning.py            [AGENT 1 — intact]
    learning/                [AGENT 1 — intact]
    context/  db/  logging/  ws/  subjects/  config.py
    subjects/definitions/    [V5.2 MODIFIÉ — python/biology/computer_networks/mathematics.yaml]
    knowledge/               [base de cours réelle, sections ## topic]
  tests/
    test_v52_unit.py         [V5.2 NOUVEAU — 58 assertions §43–§52+sandbox+§38]
    _scratch_agent_pattern.py [V5.2 scratch — à supprimer]
    test_v6_integration.py  test_v6_learning.py   [AGENT 1]
frontend/src/
  types/agent.ts  api/agent.ts  hooks/useChat.ts  components/chat/ToolStatusPanel.tsx
  [→ V5.2 : à modifier pour CodeEditor/ActivityFeed/panneaux/événements]
  api/learning.ts  types/learning.ts  components/memory/LearningProfileCard.tsx  [AGENT 1]
```

**Conclusion** : le cœur backend V5.2 (tools interactifs, état d'activité persisté, sandbox,
API, événements, tests critiques) est **opérationnel et prouvé par 55 assertions**. Restent :
1 fix de bug (`run_tests`), 2 calibrages de test, tout le frontend d'affichage, le commit.
