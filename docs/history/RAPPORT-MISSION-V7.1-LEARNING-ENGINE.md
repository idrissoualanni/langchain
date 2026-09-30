# RAPPORT — MISSION V7.1 : LEARNING ENGINE — décision pédagogique déterministe

> **Date** : 2026-09-19 — **Statut** : ✅ Terminé
> **Objectif** : stabiliser et documenter le moteur de décision pédagogique
> déterministe : « quelle est la meilleure prochaine action pour cet étudiant,
> dans ce contexte ? » — sans en faire un second agent LLM.

---

## A. Résumé

Le Learning Engine (V7) est **entièrement implémenté et vert** (0 modification
de code nécessaire). La mission V7.1 a consisté à **auditer** le code réel,
**vérifier** les tests (40/40 + régression), et livrer les livrables manquants :
documentation d'architecture (`docs/architecture/learning-engine.md`) et ce rapport.

Le moteur est une couche **métier pure et déterministe** : il consomme le
`BuiltContext` (sortie des nodes d'orchestration), produit UNE `LearningDecision`,
et ne déclenche jamais lui-même de tool, de LLM, de recherche ni d'écriture de
profil.

---

## B. État initial (avant mission V7.1)

| Élément | État |
|---------|------|
| `backend/app/learning/` | Présent (V7, commit `47bdd9e`) : `decision.py`, `engine.py`, `rules.py`, `schemas.py`, `learning_context.py`, `learning_profile.py` |
| Tests | `test_v7_learning_engine.py` existant (parties A–C unitaires, D intégration serveur) |
| Intégration orchestration | Node `learning` câblé (`orchestration.py:learning_node`) |
| Intégration prompt | Middleware orchestré + historique, bloc `LEARNING STRATEGY` |
| Docs / rapport | **Absents** → livrés par cette mission |

---

## C. Audit (vérifié dans le code, avant modification)

| # | Constat | Localisation |
|---|---------|--------------|
| A | **Contrat `LearningDecision`** complet : `action` Literal 12 valeurs, `subject/topic`, `reason`, `confidence [0..1]`, `priority [0..10]` (int), `activity_id`, `recommended_tool`, `metadata` ; `extra=forbid`. | `learning/decision.py` |
| B | **Règles centralisées** : `MASTERY_THRESHOLDS` (weak/développ. 0.40/0.70/0.85), `CONFIDENCE_LOW/HIGH`, `MIN_ATTEMPTS_TO_ADVANCE`, trajectoire (fenêtre 3, delta 0.02), stale 14 j, pondérations `W_*` nommées + `score_priority`. | `learning/rules.py` |
| C | **Hiérarchie de décision §8 respectée** : activité courante > clarification > sécurité knowledge > zones/confiance/weak points > goals > défaut answer. | `learning/engine.py:_decide_impl` |
| D | **Garde-fous respectés** : aucun appel routage/recherche/web/écriture profil depuis le moteur ; `decide(context, user_id, thread_id)` consume `BuiltContext`. | `engine.py` (testé G1–G3) |
| E | **Transitions d'activité** §34 : `ACTIVITY_TRANSITIONS` par statut ; `waiting_for_answer` n'autorise jamais `advance_topic`. | `learning/decision.py` |
| F | **Observabilité** : `LEARNING_ENGINE_START/DECISION/END/ERROR` avec user_id, thread_id, action, reason, confidence, priority, recommended_tool ; pas de system prompt/secret/message complet. | `engine.py`, `app/logging/events.py` |
| G | **Intégration node** : `learning_node` appelle réellement `decide` sur `built_context`, stocke `model_dump()` dans `state["learning_decision"]`. | `app/agent/orchestration.py:219` |
| H | **Intégration prompt** : `add_learning_strategy_block` expose Action/Sujet/Topic/Raison ; ne JAMAIS exposer scores internes/poids/priorité ; le LLM présente la stratégie en langage naturel. | `app/context/prompt_builder.py:302` |
| I | **Isolation/cross-thread** : profil par `user_id` (SqliteStore), activité par `thread_id` (checkpointer). | `learning_profile.py`, testé S13/S14 |
| J | **Non-régression** : V10 16/16, V11 31, V6.7 30, V6.8 models 10, V5.2 §43–§50, V7 engine 40/40 — tous verts. | `backend/tests/` |

---

## D. Intégration orchestration (production)

```
ROUTER → RETRIEVAL → FALLBACK → CONTEXT → LEARNING → AGENT → RESPONSE
                                                 │
                    decide(built_context, user_id, thread_id) → learning_decision
                                                 │
                    middleware : build_system_prompt + add_learning_strategy_block
```

- Le node **`learning`** lit `built_context` (déjà assemblé par le node
  `context`), appelle `decide(...)`, écrit `learning_decision` en dict.
- Le middleware (chemin orchestré) consomme `request.state.built_context` +
  `learning_decision` SANS re-exécuter le pipeline ; le chemin historique
  (sous-graphe seul) reconstruit contexte + décision — non-régression.
- Le bloc `LEARNING STRATEGY` guide le sous-graphe `agent` (model ⇄ tools).

---

## E. Schéma de décision (rappel)

`LearningDecision.action` ∈ {answer, explain, practice, hint, evaluate, quiz,
review, deepen, advance_topic, clarify, continue_activity, complete_activity}.

`recommended_tool` ∈ {create_exercise, create_quiz, evaluate_answer,
assess_understanding, give_hint, propose_review} — **recommandation** : seul
l'orchestration décide de l'appel réel.

---

## F. Résolution des conflits (tests §43)

1. **Activité en cours > tout** : `waiting_for_answer` + mastery faible + goal
   actif → `evaluate` (l'activité prime).
2. **Weak point > advance** : mastery 0.88 strong + weak point récent →
   `practice` ciblé.
3. **Ambiguïté < activité** : routing ambiguous + activité en cours → l'activité
   prime (evaluate/continue_activity).

---

## G. Outils / actions — responsabilités

| Action | Tool recommandé | Usage |
|--------|-----------------|-------|
| practice | `create_exercise` | consolider une zone developing ou un weak point |
| quiz | `create_quiz` | confirmer une maîtrise sans avancer |
| evaluate | `evaluate_answer` / `assess_understanding` | valider une réponse / une estimation |
| hint | `give_hint` | activité en cours bloquée |
| review | `propose_review` (ou `create_exercise`) | régression, stale, zone weak |

Le moteur ne déclenche **jamais** lui-même ces outils.

---

## H. Tests et résultats

### Référentiel V7 (déterministe, sans serveur — parties A–C)

- **§6/§12 zones** : seuils nommés, 4 zones + unknown — 2 tests.
- **§11 trajectoire** : progression, régression, plateau, unknown — 4 tests.
- **§42 scénarios** : not_started, mastery weak/developing/strong, confiance
  basse (2), weak point, goal, activity (3), ambiguous, knowledge absent,
  transitions (3), isolation A/B, cross-thread — **17 plus 2 trajectoires réelles**.
- **§43 conflits** : 3 tests. **§44 stabilité** : 2 tests.
- **Garde-fous source** : G1 (pas d'écriture), G2 (pas de routing/recherche),
  G3 (consomme BuiltContext) — 3 tests.

**Résultat : 40/40 PASS** (`TESTS V7 LEARNING ENGINE: OK`).

### §45 intégration LLM réelle

Suite C nécessite serveur + LLM ; exécutée séparément (bloquée ce jour par le
quota Ollama cloud — HTTP 429), le test est **sauté en mode SKIP_LLM_TESTS=1**
sans impacter les parties déterministes.

### Régression (baseline, avant/après — aucune modification de code)

| Suite | Résultat |
|-------|----------|
| `test_v10_context_documents.py` | 16/16 PASS |
| `test_v11_document_web.py` | 31 PASS |
| `test_v67_output.py` | 30 PASS |
| `test_v68_models.py` | 10 PASS |
| `test_v52_unit.py` | §43–§50 PASS (échec §51 = baseline connue, identité Clerk) |
| `test_v7_learning_engine.py` | 40/40 PASS |

Suites live LLM (`test_v6_learning`, `test_v71_semantic`, `test_v65`,
`test_v66`, `test_final_integration`) : timeout / quota Ollama — environnement,
pas une régression.

---

## I. Observabilité

Événement `LEARNING_DECISION` exposé dans les logs : `action`, `reason`
(tronquée 200 car.), `confidence`, `priority`, `recommended_tool` — visible dans
LangSmith projet « app » sur le graphe réel. Aucun secret ni système prompt loggé.

---

## J. Frontend

Aucune nouvelle UI requise (V7.1) : la décision alimente le prompt du LLM qui
produit naturellement la réponse ; les cards existantes (ExerciseCard, QuizCard,
EvaluationCard, HintCard, CodeActivityCard, LearningProfileCard,
ContextInspectorCard) restent les représentations frontend. Le Context Inspector
(`/api/context/preview`) expose `learning_strategy` + bloc `LEARNING STRATEGY`
du prompt.

---

## K. Arborescence réelle (backend/app/learning)

```
learning/
├── __init__.py            # Learning Profile V6 : playback
├── decision.py            # LearningDecision, LearningAction, ACTIVITY_TRANSITIONS
├── engine.py              # decide(context, user_id, thread_id) — couche pure
├── rules.py               # seuils/poids/zonage/trajectoire centralisés
├── schemas.py             # LearningProfile, LearningContextInfo, observations...
├── learning_context.py    # get_learning_context (sélection pertinente)
└── learning_profile.py    # persistence SqliteStore + intégration d'observations
```

Wiring : `orchestration.py:learning_node` → `engine.decide` ;
`context.builder` → `learning_context.get_learning_context` ;
`middleware`/`prompt_builder` → `add_learning_strategy_block`.

---

## L. Limitations connues

1. **Trajectoire totalement observé** : `read_trajectory` démarre à "unknown"
   tant qu'il n'y a pas 2 scores exploitables — le moteur ne devine pas une
   tendance.
2. **Pas de spaced repetition avancée** : `is_stale` (14 j) est une révision
   simple, délibérément.
3. **Quota Ollama cloud** : l'intégration LLM §45 et quelques suites live sont
   actuellement bloquées (429) — sans impact sur la couche de décision.
4. **`subject_mastery`** : utilisé pour attribution de contexte, pas comme
   signal de décision — choix documenté.

---

## M. Livrables

| Livrable | Emplacement |
|----------|-------------|
| Documentation d'architecture | `docs/architecture/learning-engine.md` |
| Ce rapport | `docs/history/RAPPORT-MISSION-V7.1-LEARNING-ENGINE.md` |
| Tests | `backend/tests/test_v7_learning_engine.py` (40/40) |
| Code | `backend/app/learning/` (V7, non modifié — audit-confirmé) |

*Rapport généré par l'assistant, conforme au code réel et aux résultats de tests
observés le jour de la mission.*