# Learning Engine — architecture du moteur de décision pédagogique (V7 / V7.1)

> **Fichier de cartographie du moteur ACTUEL** — encapsule la couche de décision
> pédagogique déterministe de l'agent tutor. Cette doc documente le code réel
> (`backend/app/learning/`) validé par la mission V7.1.

---

## 1. Rôle et position dans le pipeline

```
ROUTER → RETRIEVAL → FALLBACK → CONTEXT BUILDER
                                    │  BuiltContext (V6.8.1 canonique)
                                    ▼
                             LEARNING ENGINE
                                    │  LearningDecision
                                    ▼
              Dynamic Prompt (LEARNING STRATEGY) → LLM → Tools → AgentResponse
```

Le Learning Engine répond à la question : « Quelle est la meilleure prochaine
action pédagogique pour cet étudiant, dans ce contexte précis ? ».

Le moteur est **une couche métier pure** :

- PAS un agent / un graphe / un LLM (§2 du brief).
- Ne **modifie jamais** le Learning Profile — lecture seule (`decide()` n'écrit
  rien ; toutes les écritures passent par les tools pédagogiques).
- Ne **recrée pas** la recherche, le routing ni le web — il consomme le
  `BuiltContext` que les nodes d'orchestration ont déjà construit.
- **Déterministe** : mêmes entrées → même décision (testé §44).

---

## 2. Module `backend/app/learning/` — responsabilités

| Fichier | Responsabilité |
|---------|----------------|
| `schemas.py` | Contrats de données : `LearningProfile`, `SubjectLearningState`, `TopicLearningState`, `LearningGoal`, `LearningObservation`, `LearningContextInfo`. |
| `decision.py` | Contrat de décision : `LearningDecision`, type `LearningAction` (12 actions), `ACTIVITY_TRANSITIONS`. |
| `rules.py` | Règles déterministes **centralisées** : `MASTERY_THRESHOLDS`, `CONFIDENCE_LOW/HIGH`, `MIN_ATTEMPTS_TO_ADVANCE`, trajectoire (`read_trajectory`), fraîcheur (`is_stale`), pondérations (`W_*` + `score_priority`), `knowledge_available`. |
| `engine.py` | `decide(context, user_id='', thread_id='')` → la décision, avec hiérarchie §8 et observabilité. |
| `learning_context.py` | `get_learning_context(...)` → sélection du profil PERTINENT (source « learning » du Context Builder). |
| `learning_profile.py` | Persistance Lecture/Écriture du profil (SqliteStore, namespace `users/learning`), intégration d'observations. |

---

## 3. Schéma de décision — `LearningDecision`

| Champ | Type | Rôle |
|-------|------|------|
| `action` | Literal (12) | `answer, explain, practice, hint, evaluate, quiz, review, deepen, advance_topic, clarify, continue_activity, complete_activity` |
| `subject` / `topic` | str \| None | Cible de la décision (routée, jamais devinée) |
| `reason` | str | Raison lisible FR (exposée au prompt et à l'Inspector) |
| `confidence` | float [0..1] | Confiance de la décision |
| `priority` | int [0..10] | Score de priorité agrégé (ordre RELATIF des règles, pas un seuil absolu) |
| `activity_id` | str \| None | Activité ciblée si la décision porte sur une activité en cours |
| `recommended_tool` | str \| None | Tool suggéré (`create_exercise`, `evaluate_answer`, `give_hint`, `create_quiz`, `assess_understanding`, ...) — **recommandation, jamais appel direct** |
| `metadata` | dict | Alternatives, trajectoire, détail de scoring — jamais affiché brut |

`model_config = {"extra": "forbid"}` : le contrat est strict (testé ST2).

Frontière métier (jamais fusionnées) :

- `LearningContextInfo` = **faits** de progression (ce qui est observé),
- `LearningDecision` = **choix** pédagogique (ce qu'il faut faire),
- `AgentResponse` = **représentation** frontend (ce qui est affiché).

---

## 4. Règles centralisées (`rules.py`)

### Zones de maîtrise (§12)

```
MASTERY_THRESHOLDS = { weak: 0.40, developing: 0.70, proficient: 0.85, strong: 1.01 }
[0.00, 0.40) weak · [0.40, 0.70) developing · [0.70, 0.85) proficient · [0.85, 1.00] strong
mastery None → "unknown"  (jamais inventé)
```

### Confiance / tentatives (§13)

- `CONFIDENCE_LOW = 0.40`, `CONFIDENCE_HIGH = 0.70` — une estimation peu fiable
  ne fait jamais avancer de topic.
- `MIN_ATTEMPTS_TO_ADVANCE = 2` — 2 essais fiables avant d'avancer.

### Trajectoire (§11)

- `TRAJECTORY_WINDOW = 3` derniers scores , `TRAJECTORY_MIN_DELTA = 0.02`,
  `TRAJECTORY_STALE_DAYS = 14`.
- `read_trajectory([0.30, 0.42, 0.58]) == "progression"` ; de même à la baisse →
  `"regression"` ; pente faible → `"plateau"` ; < 2 scores → `"unknown"`.

### Pondérations de priorité (§22)

```
W_CURRENT_ACTIVITY = 10 · W_ACTIVE_GOAL = 4 · W_WEAK_POINT = 5
W_LOW_MASTERY = 4 · W_REGRESSION = 5 · W_LOW_CONFIDENCE = 3 · W_STALE_TOPIC = 2
```

`priority = min(10, Σ poids des signaux actifs)` — l'ordre relatif documente les
conflits (§43 : Activité > besoin > goal > nouveau topic).

---

## 5. Hiérarchie de décision (`engine.decide`)

1. **Activité courante PRIME** (statut ∈ `_BLOCKING_STATUSES` :
   `waiting_for_answer, waiting_for_retry, evaluating, giving_hint,
   checking_understanding`) → `evaluate` (si réponse à évaluer) ou
   `continue_activity`. Jamais de nouveau topic pendant une activité.
2. **Routing `ambiguous`** → `clarify` (candidats transmis en metadata ; pas de
   choix arbitraire).
3. **Sécurité knowledge** (pas de cours exploitable) → `answer`, sans activité
   fabriquée (le fallback V6.6 a déjà tranché).
4. **Pas de profil / `not_started`** → `explain` (premier contact, pas d'erreur ;
   `recommended_tool=create_exercise` si `supported`).
5. **Trajectoire + zones + confiance + weak points + goals** :
   - régression → `review` ; confiance basse sur zone haute → `evaluate` ;
   - weak point récent → `practice` ciblé (toutes zones, passe avant advance) ;
   - zone `weak` → `evaluate` (si estimation non fiable) sinon `review` ;
   - zone `developing` → `practice` (`create_exercise` puis `create_quiz`) ;
   - zone `proficient` → `review` si stale sinon `deepen` ;
   - zone `strong` → `advance_topic` (goal actif orienté sinon topic suivant),
     ou `quiz` de confirmation si tentatives < 2.
6. **Défaut `answer`** (et repli honnête en cas d'exception §19).

Toute erreur interne du moteur → `LEARNING_ENGINE_ERROR` + `answer` de repli :
le run ne crash jamais.

---

## 6. Intégration orchestration

- Node **`learning`** (`backend/app/agent/orchestration.py:learning_node`) :
  `decide(BuiltContext.model_validate(state["built_context"]), user_id, thread_id)`
  → écrit `state["learning_decision"]` (dict, `model_dump()`).
- Node **`context`** : `build_context(...)` produit `built_context` dont
  `context.learning` provient de `get_learning_context(...)` (source n°7 du
  Context Builder).
- Middleware **`tutor_dynamic_prompt`** (chemin orchestré) : lit
  `request.state.built_context` + `learning_decision` → `build_system_prompt` +
  `add_learning_strategy_block`.
- Chemin historique (sous-graphe seul, non-orchestré) : `_build_context_prompt`
  → `build_context` → `decide` → même présentation (non-régression).

### Bloc `LEARNING STRATEGY` (`prompt_builder.add_learning_strategy_block`)

Exposé au LLM : `Action`, `Sujet`, `Topic`, `Raison` lisible + instruction par
action. **Jamais exposés** : scores internes, poids, priorité brute, metadata,
algorithme de scoring (testé).

---

## 7. Observabilité (`app/logging/events.log_event`)

| Événement | Émis | Contenu extra |
|-----------|------|---------------|
| `LEARNING_ENGINE_START` | entrée `decide` | subject, topic |
| `LEARNING_ENGINE_ERROR` | exception moteur | erreur tronquée (300 car.) |
| `LEARNING_DECISION` | décision produite | action, reason (200 car.), confidence, priority, recommended_tool |
| `LEARNING_ENGINE_END` | sortie `decide` | action |

Aucun système prompt, secret, message complet ou profil complet n'est loggé.

---

## 8. Points de vigilance (audit V7.1)

1. **`decide()` est une couche pure** : les garde-fous sont testés par analyse de
   source (G1 : pas d'écriture profil ; G2 : pas de router/recherche ; G3 :
   consomme `BuiltContext`).
2. **Le rendu est portable** : aucune dépendance à l'Ollama pour la décision —
   les tests sont 100 % déterministes (fake model pour l'intégration LLM).
3. **Appartenance des données** : le profil est stocké par `user_id`
   (namespace `users/learning`), l'activité par `thread_id` (checkpointer) —
   l'isolation A/B et le cross-thread sont testés (§42 S13/S14).
4. **Le moteur ne décide QUE de la pédagogie** : la trajectoire est lue en
   lecture seule depuis `list_observations` — le moteur n'intègre JAMAIS
   d'observation (rôle du `Profile Updater`).

*Documentation générée par l'assistant — conforme au code réel, mission V7.1.*