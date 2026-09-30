# MISSION — AUDIT COMPLET + CLEANUP DU PROJET AGENT

## 0. Mission

Effectuer un **audit exhaustif puis un cleanup contrôlé** du projet avant la prochaine grande phase :

```text
V10 — USER KNOWLEDGE + RAG
```

Cette mission couvre :

```text
Agent Core
Tools
Memory
Thread State
Persistence
Learning Profile
Learning Engine
Context
Prompt
Router
Search
Fallback
AgentResponse
Middleware
Model configuration
Frontend
Frontend Memory UX
API
SSE
Tests
Configuration
Scripts
```

Objectifs :

1. Comprendre exactement le fonctionnement réel du système.
2. Identifier les doublons, anciennes implémentations, éléments mal placés, code mort et fichiers inutiles.
3. Supprimer réellement les éléments confirmés inutiles.
4. Vérifier la non-régression.
5. Produire un rapport complet avant le passage à V10.

---

# 1. PHASES DÉJÀ TERMINÉES

Le projet est considéré comme stabilisé jusqu'à :

```text
V0   Foundation
V1   Users / Threads / Persistence
V2   User Memory
V3   MemoryFacts
V4   Subject / Knowledge / Router
V5   Context Engineering
V5.2 Pedagogical Tools
V6   Learning Profile
V6.5 Search / Retrieval
V6.6 Fallback Intelligence
V6.7 Structured Agent Output + UX
V6.8 Context Budget + Model Capabilities
V7   Learning Engine
V7.1 Retrieval avancé / hybride
V8   Clerk
V9   Assistant UI + User App
```

Prochaine phase :

```text
V10 — USER KNOWLEDGE + RAG
```

Ne pas implémenter V10 pendant cette mission.

---

# 2. HORS PÉRIMÈTRE

NE PAS ajouter :

```text
RAG vectoriel
Qdrant
embeddings
User Document Knowledge
Langfuse
OpenTelemetry
HITL
Multi-Agent
nouveau provider
nouveau modèle obligatoire
vision
audio
```

Langfuse sera ajouté **après le RAG et le retrieval avancé**.

Cette mission est exclusivement :

```text
AUDIT
+
CLEANUP
```

---

# 3. ORDRE OBLIGATOIRE

Respecter exactement cet ordre :

```text
0. Git + état initial + baseline
        ↓
1. Inventaire complet
        ↓
2. Cartographie de l'architecture réelle
        ↓
3. Audit Agent Core
        ↓
4. Audit Tools
        ↓
5. Audit Memory + Persistence
        ↓
6. Audit Learning Profile + Learning Engine
        ↓
7. Audit Context + Prompt + Router + Subject Registry
        ↓
8. Audit Search + Fallback
        ↓
9. Audit AgentResponse + API + SSE
        ↓
10. Audit Middleware + Models
        ↓
11. Audit Frontend
        ↓
12. Audit Frontend Memory UX
        ↓
13. Audit hardcodes + code mort + doublons
        ↓
14. Classification des éléments
        ↓
15. Plan de cleanup
        ↓
16. Cleanup par petits lots
        ↓
17. Tests après chaque lot
        ↓
18. Second audit
        ↓
19. Validation finale
        ↓
20. Rapport final
```

**Ne pas supprimer de fichiers au début de l'audit.**

---

# 4. ÉTAPE 0 — GIT ET ÉTAT INITIAL

Avant toute modification :

```bash
git status
git branch
git log --oneline -10
```

Identifier :

```text
branche actuelle
commit actuel
fichiers modifiés
fichiers non suivis
```

Créer une branche dédiée si compatible avec le workflow :

```bash
git checkout -b audit-cleanup
```

Ne pas écraser le travail existant.

---

# 5. BASELINE DES TESTS

Lancer toutes les suites réellement présentes.

Inclure au minimum si elles existent :

```text
test_v5_architecture.py
test_v5_integration.py
test_v52_unit.py
test_v6_learning.py
test_v6_integration.py
test_final_integration.py
test_v65_search.py
test_v66_fallback.py
test_v67_output.py
test_v68_context_budget.py
test_v68_models.py
tests/test_agent_response.py
tests V7
tests Clerk
tests frontend
```

Puis :

```bash
npm run build
npx tsc -b
```

si disponibles.

Noter précisément :

```text
nombre total
PASS
FAIL
SKIP
```

Cette valeur devient la **baseline**.

Ne jamais supprimer ou désactiver un test pour obtenir un PASS.

Si un test échoue déjà avant le cleanup :

```text
STOP
documenter
ne pas attribuer l'échec au cleanup
```

---

# 6. ÉTAPE 1 — INVENTAIRE COMPLET

Construire l'arborescence réelle du repository.

Inspecter notamment :

```text
backend/
frontend/
tests/
scripts/
configuration/
schemas/
knowledge/
```

si présents.

Ne pas inventer de fichiers.

Identifier :

```text
modules
services
schemas
routes
tools
components
stores
tests
configurations
scripts
```

---

# 7. ÉTAPE 2 — CARTOGRAPHIE DE L'ARCHITECTURE RÉELLE

Reconstituer le chemin réel d'une requête.

Partir notamment de :

```text
POST /api/chat
```

et :

```text
GET /api/chat/stream
```

si ces routes existent.

Tracer exactement :

```text
Frontend
 ↓
API
 ↓
Clerk / Auth
 ↓
User resolution
 ↓
Thread resolution
 ↓
Runner
 ↓
Graph
 ↓
Middleware
 ↓
Router
 ↓
Context
 ↓
Prompt
 ↓
Model
 ↓
Tools
 ↓
State / Store
 ↓
Memory / Learning updates
 ↓
Response Normalizer
 ↓
AgentResponse
 ↓
SSE / API
 ↓
Frontend Renderer
```

Adapter le diagramme au code réellement trouvé.

Pour chaque étape :

```text
fichier
fonction
responsabilité
```

---

# 8. ÉTAPE 3 — AUDIT AGENT CORE

Inspecter notamment :

```text
graph.py
runner.py
state.py
middleware.py
prompts.py
tools.py
```

et tous les modules réellement associés.

Vérifier :

```text
create_agent
state_schema
context_schema
middleware
tools
model
checkpointer
store
```

Déterminer :

```text
Quel State ?
Quel Runtime Context ?
Quel Store ?
Quel Checkpointer ?
Quels middleware ?
Quels tools ?
Quel modèle ?
```

Rechercher les anciennes implémentations parallèles.

---

# 9. AUDIT RUNNER

Déterminer précisément le rôle du runner.

Rechercher les responsabilités dupliquées :

```text
préparation manuelle du contexte
préparation manuelle du prompt
gestion manuelle du State
gestion manuelle de la mémoire
fallback
normalisation
orchestration
```

Classer chaque responsabilité :

```text
LangChain/LangGraph natif
business logic
infrastructure
legacy
doublon
```

---

# 10. AUDIT STATE

Lister tous les champs du State.

Pour chaque champ :

```text
nom
type
producteur
consommateurs
persisté ?
thread-scoped ?
utilisé par LLM ?
utilisé par tools ?
utilisé par middleware ?
nécessaire ?
```

Classer :

```text
KEEP
REMOVE
MOVE
DERIVE
REVIEW
```

Vérifier les usages indirects avant toute suppression.

---

# 11. AUDIT RUNTIME CONTEXT

Vérifier l'utilisation réelle de :

```text
user_id
thread_id
model
environment
permissions
feature flags
```

Déterminer ce qui appartient au Runtime Context.

Rechercher les injections inutiles dans les prompts.

Notamment :

```text
user_id
thread_id
```

ne doivent pas être ajoutés au system prompt uniquement parce qu'ils existent dans le backend.

---

# 12. ÉTAPE 4 — AUDIT COMPLET DES TOOLS

Rechercher toutes les formes de tools :

```python
@tool
```

et :

```text
StructuredTool
Tool
create_tool
tool registry
tools=[
```

ainsi que les registrations dynamiques.

Créer un tableau :

| Tool | Fichier | Catégorie | Enregistré | Appelants | Tests | Décision |
|---|---|---|---|---|---|---|

Catégories :

```text
PEDAGOGICAL
SEARCH
KNOWLEDGE
MEMORY
LEARNING
CODE
UTILITY
SYSTEM
OTHER
```

---

# 13. POUR CHAQUE TOOL

Déterminer :

```text
rôle
inputs
outputs
appelants
registration
LLM peut-il le sélectionner ?
état modifié ?
Store modifié ?
Memory modifiée ?
Learning Profile modifié ?
tests
```

Puis :

```text
KEEP
REMOVE
MERGE
REFACTOR
MOVE
REVIEW
```

---

# 14. TOOLS INUTILISÉS

Un tool peut être supprimé seulement si :

```text
non enregistré
OU
aucun appel réel
ET
aucune fonctionnalité actuelle n'en dépend
ET
aucun test valide ne l'utilise
ET
aucune registration dynamique
ET
aucun script/route ne l'utilise
ET
aucun remplacement nécessaire
```

Ne jamais supprimer uniquement parce qu'il semble ancien.

---

# 15. TOOLS PÉDAGOGIQUES

Inspecter notamment :

```text
create_exercise
evaluate_answer
give_hint
execute_python
```

et tous les équivalents.

Déterminer si la logique appartient réellement à :

```text
tool
service métier
helper
```

Rechercher les doublons.

---

# 16. TOOLS MEMORY

Identifier tous les tools touchant la mémoire.

Déterminer :

```text
le LLM doit-il réellement appeler ces tools ?
```

ou :

```text
la mémoire est-elle gérée automatiquement ?
```

Ne rien supprimer avant d'avoir compris le flux.

---

# 17. TOOLS SEARCH / KNOWLEDGE

Inspecter :

```text
local search
web search
retrieval
ranking
SearchResult
SearchResponse
```

Vérifier qu'il n'existe pas plusieurs moteurs concurrents.

---

# 18. ÉTAPE 5 — AUDIT MEMORY + PERSISTENCE

Identifier tous les systèmes :

```text
Thread State
SqliteSaver
User Memory
MemoryFacts
SqliteStore
Learning Profile
localStorage
React state
Zustand
```

Déterminer leurs frontières.

---

# 19. THREAD STATE

Le Thread State représente :

```text
état court terme du thread
conversation actuelle
activité en cours
```

Vérifier :

```text
messages
activity state
thread context
```

Déterminer ce qui est réellement persisté par :

```text
SqliteSaver
```

---

# 20. USER MEMORY

Déterminer précisément ce qui constitue :

```text
User Memory
```

Identifier :

```text
où stockée
qui écrit
qui lit
qui modifie
comment sélectionnée
comment injectée dans le contexte
```

---

# 21. MEMORYFACTS

Reconstituer le flux réel :

```text
User Message
 ↓
Memory Decision
 ↓
MemoryFact
 ↓
Validation
 ↓
SqliteStore
 ↓
Retrieval
 ↓
Context Builder
 ↓
Dynamic Prompt
 ↓
LLM
```

Si le flux réel est différent, documenter le flux réel.

Identifier :

```text
qui décide
qui extrait
qui valide
qui écrit
qui lit
```

---

# 22. LEARNING PROFILE VS USER MEMORY

Vérifier absolument :

```text
User Memory
≠
Learning Profile
```

Learning Profile :

```text
mastery
confidence
weak_points
strengths
goals
assessments
progression
```

User Memory :

```text
informations persistantes sur l'utilisateur
```

Identifier tous les doublons.

---

# 23. CHECKPOINTER

Inspecter :

```text
SqliteSaver
```

Rechercher :

```text
manual message persistence
duplicate thread storage
local thread persistence
```

---

# 24. STORE

Inspecter :

```text
SqliteStore
```

Documenter :

```text
namespaces
keys
reads
writes
callers
```

Vérifier :

```text
user_id
namespace
ownership
isolation
```

---

# 25. MEMORY ISOLATION

Tester :

```text
User A
 ↓
Memory Fact A
 ↓
Thread B
 ↓
Fact A disponible
```

Puis :

```text
User B
 ↓
ne doit jamais voir Fact A
```

Tester aussi :

```text
Thread A
 ↓
Thread B
```

La User Memory doit rester cross-thread.

---

# 26. MEMORY DANS LE CONTEXTE

Identifier exactement comment :

```text
Store
 ↓
Context Builder
 ↓
Dynamic Prompt
 ↓
LLM
```

ou le flux réel.

Rechercher les injections multiples.

---

# 27. FRONTEND MEMORY

Inspecter :

```text
/settings/memory
```

et les composants associés.

Déterminer :

```text
API
données affichées
actions disponibles
actions réellement supportées
```

Le frontend ne doit pas gérer le moteur de mémoire.

---

# 28. FRONTEND MEMORY UX

Tester :

```text
login
 ↓
thread A
 ↓
message
 ↓
memory
 ↓
thread B
```

Vérifier :

```text
cross-thread memory
user isolation
reload
new thread
thread switch
logout/login
```

Le scope de User Memory doit être :

```text
user_id
```

et non :

```text
thread_id
```

---

# 29. ÉTAPE 6 — LEARNING PROFILE + LEARNING ENGINE

Inspecter :

```text
learning profile
learning engine
```

Déterminer :

```text
stockage
lecture
écriture
appelants
entrées
sorties
```

Rechercher les anciennes versions.

Ne pas créer de second Learning Engine.

---

# 30. ÉTAPE 7 — CONTEXT

Inspecter le Context Builder.

Lister :

```text
Runtime Context
Thread State
User Memory
Learning Profile
Subject
Topic
Knowledge
Search
Activity
```

Pour chaque source :

```text
sélection
priorité
format
limite
consommateur
```

Rechercher :

```text
Context Builder A
Context Builder B
Legacy Context Builder
```

---

# 31. DYNAMIC PROMPT

Inspecter :

```text
CORE_PROMPT
dynamic_prompt
prompt builder
middleware
```

Déterminer :

```text
statique
dynamique
```

Rechercher :

```text
anciens prompts
subject prompts dupliqués
memory prompts dupliqués
context formatting dupliqué
```

---

# 32. ROUTER

Inspecter :

```text
subject
topic
confidence
status
candidates
```

Vérifier les statuts :

```text
supported
ambiguous
unsupported
unknown
multi_domain
```

Rechercher :

```text
keyword matching
hardcoded subjects
if subject ==
if topic ==
```

---

# 33. SUBJECT REGISTRY

Inspecter :

```text
SubjectConfig
YAML
JSON
Subject Registry
```

Rechercher :

```text
hardcoded subject names
hardcoded tools
hardcoded capabilities
hardcoded knowledge sources
```

Identifier les configurations concurrentes.

---

# 34. ÉTAPE 8 — SEARCH + FALLBACK

Inspecter :

```text
SearchResult
SearchResponse
FallbackDecision
local search
web search
General Tutor
```

Vérifier qu'il existe une logique centrale.

Rechercher les anciennes :

```text
fallbacks
if/elif
search engines
ranking
```

---

# 35. FALLBACK

Vérifier les états distincts :

```text
subject_unknown
subject_unsupported
subject_ambiguous

knowledge_insufficient
knowledge_unavailable
knowledge_error

web_unavailable
web_error
web_insufficient
```

Ne pas réduire tous les cas à :

```text
not found
```

---

# 36. ÉTAPE 9 — AgentResponse + API + SSE

Inspecter :

```text
AgentResponse
AgentAction
ResponseNormalizer
ResponseRenderer
```

Vérifier que le contrat public est :

```text
AgentResponse
```

et que le frontend ne dépend pas directement de :

```text
AIMessage
ToolMessage
Command
LangGraph State
```

---

# 37. ANCIENS RESPONSE SCHEMAS

Rechercher :

```text
ChatResponse
ExerciseResponse
QuizResponse
StreamingResponse
```

et équivalents.

Classer :

```text
KEEP
COMPATIBILITY
REMOVE
MERGE
REVIEW
```

---

# 38. SSE

Vérifier la séparation :

```text
events
≠
AgentResponse
```

Les événements restent :

```text
RUN_START
TOOL_START
TOOL_END
SEARCH_START
SEARCH_END
FALLBACK_DECISION
```

La réponse finale peut être :

```text
AGENT_RESPONSE
```

---

# 39. ÉTAPE 10 — MIDDLEWARE

Lister tous les middleware.

Pour chacun :

```text
nom
responsabilité
ordre
inputs
outputs
side effects
tests
```

Classer :

```text
nécessaire
doublon
legacy
mal placé
```

---

# 40. MODEL CONFIGURATION

Inspecter :

```text
model
provider
capabilities
structured output
tool calling
context window
```

Rechercher :

```text
hardcoded model
environment model
SubjectConfig model
Model Registry
```

Identifier les sources contradictoires.

---

# 41. ÉTAPE 11 — FRONTEND

Inspecter :

```text
frontend/src/
```

notamment :

```text
assistant
learning
profile
settings
components
stores
services
api
```

Rechercher :

```text
old ChatPage
old Sidebar
old ThreadList
old response types
old stores
old API clients
duplicate components
```

---

# 42. FRONTEND SOURCE OF TRUTH

Identifier la source de vérité pour :

```text
user
activeThread
messages
model
memory
learning
```

Rechercher les duplications :

```text
Zustand
localStorage
React Context
URL
component state
```

Classer :

```text
KEEP
DERIVE
REMOVE
REVIEW
```

---

# 43. SIDEBAR / THREADLIST

Vérifier :

```text
Sidebar
=
application navigation
```

et :

```text
ThreadList
=
conversation management
```

Il ne doit pas y avoir deux rails visuels inutiles.

Vérifier :

```text
desktop
mobile
thread selection
new thread
rename
archive
delete
```

Ne pas conserver de faux contrôles no-op.

---

# 44. ASSISTANT UI

Vérifier :

```text
official primitives
custom wrappers
local copies
duplicate elements
```

Ne pas refaire le système Assistant UI.

---

# 45. LEARNING PAGES

Inspecter :

```text
/learning
/learning/progress
/learning/subjects
/learning/subjects/:subjectId
/learning/topics
/learning/goals
/learning/reviews
/learning/history
/learning/for-you
```

Rechercher :

```text
duplicate pages
mock data permanent
unused components
fake backend actions
```

---

# 46. PROFILE + SETTINGS

Inspecter :

```text
/profile
/settings
/settings/profile
/settings/appearance
/settings/learning
/settings/memory
/settings/notifications
/settings/privacy
```

Vérifier les fonctionnalités réellement supportées.

Supprimer les fonctionnalités frontend qui prétendent fonctionner mais ne sont pas connectées.

---

# 47. ÉTAPE 12 — HARDCODES

Recherche globale :

```text
if subject ==
if model ==
if provider ==
if tool ==
if knowledge ==
if fallback ==
```

Rechercher :

```text
hardcoded subjects
hardcoded tool lists
hardcoded model names
hardcoded providers
hardcoded response types
```

Classer :

```text
configuration
business logic
infrastructure
legacy
```

---

# 48. CODE MORT

Rechercher :

```text
unused imports
unused functions
unused classes
unused constants
unused schemas
unused types
unused hooks
unused components
unreachable branches
```

Avant de conclure, vérifier :

```text
dynamic imports
routes
registrations
middleware
startup
scripts
CLI
tests
```

---

# 49. ÉTAPE 13 — DÉCISION

Utiliser uniquement :

```text
KEEP
REMOVE
REFACTOR
MERGE
MOVE
DERIVE
REVIEW
FUTURE
```

Définitions :

```text
KEEP
nécessaire aujourd'hui

REMOVE
inutile et sans dépendance

REFACTOR
nécessaire mais trop complexe

MERGE
doublon avec un autre module

MOVE
responsabilité au mauvais endroit

DERIVE
ne doit pas avoir une deuxième source de vérité

REVIEW
incertitude nécessitant une décision

FUTURE
nécessaire uniquement pour une phase future
```

---

# 50. RÈGLE DE SUPPRESSION D'UN FICHIER

Un fichier peut être supprimé seulement si :

```text
imports entrants vérifiés
imports dynamiques vérifiés
registrations vérifiées
routes vérifiées
tests vérifiés
scripts vérifiés
rôle compris
dépendances critiques vérifiées
remplacement identifié si nécessaire
```

Ne jamais supprimer parce que :

```text
"je ne vois aucun import"
```

---

# 51. RÈGLE DE SUPPRESSION D'UN TOOL

Un tool peut être supprimé seulement si :

```text
non enregistré
OU
aucun appel réel
ET
aucune fonctionnalité dépendante
ET
aucun test valide
ET
aucune registration cachée
ET
aucun remplacement nécessaire
```

---

# 52. RÈGLE DE SUPPRESSION D'UN TEST

Un test peut être supprimé seulement si :

```text
le comportement n'existe plus volontairement
ET
le nouveau contrat le remplace
ET
un test équivalent existe
```

Sinon :

```text
KEEP
```

Ne jamais désactiver un test.

---

# 53. ÉTAPE 14 — PLAN DE CLEANUP

Avant les suppressions importantes, construire un plan :

```text
LOT 1
backend legacy

LOT 2
tools inutiles

LOT 3
memory duplication

LOT 4
context/prompt duplication

LOT 5
search/fallback legacy

LOT 6
old response schemas

LOT 7
frontend legacy

LOT 8
unused helpers/components
```

Adapter les lots au code réel.

---

# 54. CLEANUP PAR PETITS LOTS

Pour chaque lot :

```text
identifier
↓
modifier
↓
supprimer
↓
chercher références cassées
↓
tests
```

Ne pas faire une suppression massive en une seule opération.

---

# 55. SUPPRESSION RÉELLE

Lorsqu'un fichier est confirmé inutile :

```text
SUPPRIMER RÉELLEMENT
```

Ne pas :

```text
vider le fichier
renommer old_
renommer legacy_
déplacer dans deprecated/
```

uniquement pour le conserver.

---

# 56. MIGRATION

Si un ancien module doit être remplacé :

```text
ancien
 ↓
migration
 ↓
nouveau
 ↓
tests
 ↓
suppression ancien
```

Ne pas conserver deux implémentations fonctionnelles parallèles sans raison.

---

# 57. TESTS APRÈS CHAQUE LOT

Après chaque lot :

```text
backend tests
frontend tests
tsc
build
```

selon les outils disponibles.

Si régression :

```text
STOP
identifier
corriger
retester
```

---

# 58. TESTS FONCTIONNELS FINAUX

Tester au minimum :

```text
login
logout
assistant
new thread
thread switch
send message
SSE
AgentResponse
exercise
quiz
code
search
fallback
learning
profile
settings
memory
```

---

# 59. TESTS MÉMOIRE FINAUX

Tester :

```text
User A
 ↓
Memory
 ↓
Thread A
 ↓
Thread B
 ↓
Memory toujours disponible
```

Puis :

```text
User B
 ↓
ne voit jamais User A
```

Vérifier :

```text
Thread State
≠
User Memory

Learning Profile
≠
User Memory
```

---

# 60. TESTS CONTEXT

Vérifier que le système peut encore utiliser :

```text
subject
topic
thread
memory
learning profile
knowledge
search
activity
runtime context
```

---

# 61. TESTS TOOLS

Pour chaque tool conservé :

```text
registration
invocation
result
error handling
```

Tester particulièrement les tools pédagogiques critiques.

---

# 62. ÉTAPE 15 — SECOND AUDIT

Après cleanup, refaire les recherches :

```text
unused
legacy
deprecated
old
TODO
if subject ==
if model ==
hardcoded
duplicate
```

Comparer :

```text
BEFORE
vs
AFTER
```

Vérifier que les éléments identifiés comme supprimables ont réellement disparu.

---

# 63. AUDIT DES IMPORTS

Vérifier qu'il ne reste aucune référence cassée :

```text
backend
frontend
tests
scripts
```

---

# 64. AUDIT ARBRE FINAL

Produire :

```text
arbre initial
```

et :

```text
arbre final
```

Identifier clairement les suppressions.

---

# 65. AUDIT DE COMPLEXITÉ

Pour :

```text
Agent
Tools
Memory
Context
Search
Fallback
Learning
Frontend
```

indiquer :

```text
modules principaux
responsabilités
doublons restants
complexité notable
```

---

# 66. PRÉPARATION V10

Vérifier que l'architecture peut accueillir :

```text
User Knowledge
Documents
Retrieval
```

sans réécrire :

```text
Agent Core
Context Builder
Memory
Subject Registry
Search
Fallback
AgentResponse
Frontend
```

Le futur RAG devra pouvoir devenir une source supplémentaire :

```text
User Documents
 ↓
Retrieval
 ↓
Context Builder
```

---

# 67. NE PAS IMPLÉMENTER V10

Même si le cleanup révèle des besoins pour le RAG :

```text
documenter
```

mais :

```text
NE PAS implémenter
```

pendant cette mission.

---

# 68. NE PAS AJOUTER LANGFUSE

Langfuse sera ajouté après :

```text
V10 — User Knowledge + RAG
V11 — Retrieval avancé
```

Donc pendant cette mission :

```text
NE PAS installer Langfuse
NE PAS intégrer Langfuse
```

---

# 69. RAPPORT FINAL — STRUCTURE OBLIGATOIRE

Le rapport final doit contenir les sections suivantes.

## A. Executive Summary

```text
état initial
objectif
travail réalisé
nombre de fichiers supprimés
nombre de tools supprimés
nombre de doublons supprimés
tests avant
tests après
état final
```

## B. Git / Baseline

```text
branche initiale
commit initial
branche cleanup
commit final
git status
```

## C. Architecture réelle AVANT cleanup

Diagramme complet et fichiers associés.

## D. Agent Core

| Module | Responsabilité | Dépendances | Décision |
|---|---|---|---|

## E. Tools

| Tool | Catégorie | Fichier | Registration | Appelants | Tests | Décision |
|---|---|---|---|---|---|---|

## F. Memory

Documenter précisément :

```text
Thread State
SqliteSaver
User Memory
MemoryFacts
SqliteStore
Learning Profile
```

Pour chacun :

```text
stockage
scope
lecture
écriture
consommateurs
```

## G. Memory Flow

Fournir le flux réel :

```text
User Message
 ↓
Memory Decision
 ↓
MemoryFact
 ↓
Store
 ↓
Context
 ↓
Prompt
 ↓
LLM
```

ou le flux réellement trouvé.

## H. Frontend Memory

Documenter :

```text
/settings/memory
API
données
actions
limitations
cross-thread behavior
user isolation
```

## I. Context / Prompt

Documenter :

```text
Runtime Context
State
Store
Context Builder
Dynamic Prompt
```

## J. Search / Fallback

Documenter :

```text
Search
Ranking
FallbackDecision
General Tutor
```

## K. AgentResponse / API / SSE

Documenter :

```text
AgentResponse
ResponseNormalizer
ResponseRenderer
SSE
events
```

## L. Frontend

Documenter :

```text
Assistant
Learning
Profile
Settings
Sidebar
ThreadList
Stores
API
```

## M. Fichiers supprimés

| Fichier | Raison | Remplacement | Vérifications |
|---|---|---|---|

## N. Tools supprimés

| Tool | Raison | Remplacement | Vérifications |
|---|---|---|---|

## O. Code supprimé

Identifier :

```text
dead code
duplicate functions
old schemas
old prompts
old helpers
```

## P. Simplifications

Pour chaque simplification :

```text
AVANT
 ↓
APRÈS
```

## Q. Éléments conservés

Identifier les éléments essentiels :

```text
Agent Core
Memory
Learning
Search
Fallback
Tools
AgentResponse
Frontend
```

## R. Éléments FUTURE

Lister uniquement les éléments réellement nécessaires aux futures phases :

```text
User Knowledge
RAG
Retrieval avancé
Langfuse
HITL
Multi-Agent
Production
```

Ne pas conserver du code uniquement parce qu'il pourrait être utile.

## S. NON-RÉGRESSION

Comparer :

```text
BEFORE CLEANUP
X/X PASS

AFTER CLEANUP
X/X PASS
```

Inclure :

```text
backend
frontend
tsc
build
memory
user isolation
SSE
```

## T. Arbre réel FINAL

Fournir l'arborescence réelle après cleanup.

## U. Problèmes restants

Lister honnêtement :

```text
bugs
dette technique
limites
fonctionnalités incomplètes
```

## V. Risques avant RAG

Identifier les risques concernant :

```text
Memory
Thread State
Learning Profile
Context
Search
Fallback
User isolation
API
Frontend
```

## W. Préparation V10

Conclure :

```text
READY FOR V10
```

ou :

```text
NOT READY FOR V10
```

avec justification factuelle.

---

# 70. CRITÈRES DE RÉUSSITE

La mission est terminée si :

```text
✅ architecture réelle documentée
✅ runtime documenté
✅ Agent Core audité
✅ tous les tools inventoriés
✅ tools inutiles supprimés
✅ Memory entièrement auditée
✅ Thread State audité
✅ SqliteSaver audité
✅ SqliteStore audité
✅ MemoryFacts audités
✅ Learning Profile audité
✅ Learning Engine audité
✅ Context Builder audité
✅ Dynamic Prompt audité
✅ Router audité
✅ Subject Registry audité
✅ Search audité
✅ Fallback audité
✅ AgentResponse audité
✅ SSE audité
✅ Middleware audité
✅ Model configuration auditée
✅ Frontend audité
✅ Frontend Memory auditée
✅ hardcodes audités
✅ code mort recherché
✅ doublons identifiés
✅ fichiers inutiles supprimés
✅ code inutile supprimé
✅ anciens schemas supprimés si réellement obsolètes
✅ anciens composants supprimés si réellement obsolètes
✅ aucun test désactivé
✅ aucun test supprimé arbitrairement
✅ aucune régression
✅ memory cross-thread PASS
✅ user isolation PASS
✅ Thread State séparé de User Memory
✅ Learning Profile séparé de User Memory
✅ frontend build PASS
✅ TypeScript PASS
✅ architecture prête pour V10
```

---

# 71. RÈGLE FINALE

Cette mission doit laisser un projet :

```text
PLUS SIMPLE
PLUS CLAIR
PLUS COHÉRENT
PLUS MAINTENABLE
```

Chaque module doit avoir :

```text
une responsabilité claire
des consommateurs identifiés
des dépendances identifiées
des tests
```

Règles :

```text
SI nécessaire
→ KEEP

SI doublon
→ MERGE / REMOVE

SI remplacé
→ REMOVE l'ancien

SI inutilisé et sans dépendance
→ REMOVE

SI mal placé
→ MOVE

SI nécessaire mais complexe
→ REFACTOR

SI uniquement hypothétique
→ ne pas conserver par précaution

SI incertain
→ REVIEW avant suppression
```

Ne jamais sacrifier la stabilité simplement pour réduire le nombre de fichiers.

Le résultat attendu :

```text
CHAQUE MODULE
      ↓
A UNE RESPONSABILITÉ CLAIRE
      ↓
A DES CONSOMMATEURS IDENTIFIÉS
      ↓
N'EST PAS DUPLIQUÉ
      ↓
EST TESTÉ
```

La mission se termine uniquement après :

```text
AUDIT
+
CLEANUP
+
TESTS
+
SECOND AUDIT
+
RAPPORT FINAL
```

Prochaine phase :

```text
V10 — USER KNOWLEDGE + RAG
```

Puis :

```text
V11 — RETRIEVAL AVANCÉ
```

Puis :

```text
V12 — LANGFUSE / OBSERVABILITY
```
