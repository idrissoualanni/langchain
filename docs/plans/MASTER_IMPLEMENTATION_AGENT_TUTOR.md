# MASTER MISSION --- REFONTE ET EXTENSION DE L'AGENT TUTOR

## Architecture LangGraph + Subgraphs + Tools + Activities + Coding + Problem + Research + Video + LiveKit + MCP + Guardrails + Admin + Frontend + Production

> **Objectif :** produire une architecture cohérente et extensible à
> partir du projet existant, sans reconstruire ce qui fonctionne déjà.
>
> **Règle absolue :** auditer le dépôt réel avant toute modification.
> Les noms, chemins, versions et APIs doivent être vérifiés dans le code
> et dans la documentation officielle actuelle.

------------------------------------------------------------------------

# 1. CONTEXTE DE RÉFÉRENCE

Le projet possède déjà un socle important :

``` text
V5      Context Engineering
V5.2    Interactive Learning Tools
V6      Learning Profile
V6.5    Search / Retrieval
V6.6    Fallback
V6.7    AgentResponse
V6.8    Context Budget / Model Capabilities
V7      Parent LangGraph StateGraph
```

Architecture actuellement visée :

``` text
React
 ↓
FastAPI
 ↓
Main LangGraph StateGraph
 ↓
Router
 ↓
Retrieval
 ↓
Fallback
 ↓
Context
 ↓
Learning
 ↓
Agent
 ↓
Response
```

Le dépôt contient également des workflows Problem et Video déjà amorcés.

Les fichiers source fournis confirment notamment :

-   `problem_parse.py` : parsing structuré d'un énoncé ;
-   `problem_plan.py` : génération interne des étapes attendues ;
-   `problem_validate.py` : évaluation déterministe et artefact Markdown
    ;
-   `video_ingest.py` : localisation/upload + transcription + événements
    SSE ;
-   `video_segment.py` : segmentation pédagogique du transcript +
    validation Pydantic + persistance.

Ces fichiers doivent servir de base à la migration vers des subgraphs,
pas être remplacés sans audit.

------------------------------------------------------------------------

# 2. DOCUMENTATION OBLIGATOIRE

Avant toute implémentation, consulter la documentation officielle
correspondant aux versions réellement installées.

## LangGraph / LangChain

Étudier au minimum :

``` text
Thinking in LangGraph
Graph API
State
Nodes
Edges / conditional routing
Command
RetryPolicy
interrupt / HITL
Subgraphs
Streaming
Persistence
Runtime Context
Store
Middleware
Tools
create_agent
Structured Output
Context Engineering
Deep Research patterns
```

La philosophie à respecter est :

``` text
workflow
→ étapes discrètes
→ état minimal et brut
→ nodes minces
→ services métier
→ erreurs explicites
→ retries pour erreurs transitoires
→ checkpoints aux frontières importantes
→ subgraphs pour workflows complexes
```

Le State ne doit pas contenir des représentations dérivées qui peuvent
être reconstruites.

## MCP

Vérifier la version actuelle du MCP Python SDK et de la spécification.

Le protocole doit être traité comme une frontière d'intégration :

``` text
Tools
Resources
Prompts
```

avec les transports supportés par la version utilisée.

Pour les intégrations distantes modernes, vérifier en priorité le
transport Streamable HTTP et les mécanismes d'autorisation actuels.

## LiveKit

Étudier la documentation actuelle de LiveKit Agents :

``` text
Agent
AgentSession
Rooms
WebRTC
STT
LLM
TTS
Tools
Toolsets
MCP
Workflows
Handoffs
Video input
Video output
Frontend integration
Agent server
Deployment
Observability
```

LiveKit doit rester la couche :

``` text
realtime media
session
audio
video
WebRTC
interruptions
turn-taking
```

LangGraph reste la couche :

``` text
durable workflow
state
pedagogy
activities
research
coding
problem solving
```

## Assistant UI

Utiliser l'intégration Assistant UI déjà présente et ses APIs
officielles actuelles.

Ne pas créer une deuxième implémentation de chat.

------------------------------------------------------------------------

# 3. PRINCIPES ARCHITECTURAUX

Toujours distinguer :

``` text
LangGraph
= orchestration

Node
= étape d'un workflow

Subgraph
= workflow spécialisé complexe

Service
= logique métier réutilisable

Tool
= capacité exposée au LLM quand une invocation agentique est pertinente

Store
= données/mémoire persistantes

RAG
= retrieval de connaissances

Learning Engine
= décision pédagogique

LLM
= interaction naturelle / génération / raisonnement

AgentResponse
= contrat public frontend

LiveKit
= realtime media/session

MCP
= protocole d'intégration de capacités externes

Guardrails
= contrôle sécurité/politique
```

------------------------------------------------------------------------

# 4. MAIN GRAPH

Le Main Graph doit rester petit :

``` text
START
 ↓
Intake
 ↓
Router
 ↓
Workflow Router
 ↓
Context
 ↓
Learning Engine
 ↓
Agent
 ↓
Response
 ↓
END
```

Les subgraphs spécialisés sont sélectionnés lorsqu'un workflow complexe
est nécessaire.

Ne jamais transformer le Main Graph en catalogue de toutes les fonctions
de l'application.

------------------------------------------------------------------------

# 5. SUBGRAPH ARCHITECTURE

Créer progressivement :

``` text
ProblemSubgraph
CodingSubgraph
ResearchSubgraph
ActivitySubgraph
VideoSubgraph
DocumentSubgraph
```

Le `create_agent(...)` existant reste le sous-graphe agentique
conversationnel.

Un subgraph doit avoir :

``` text
State typé
Entrée claire
Sortie claire
Nodes internes
Tools spécialisés
Gestion d'erreurs
Streaming si nécessaire
Tests
```

Ne pas exposer son State interne au Main Graph.

------------------------------------------------------------------------

# 6. RELATION SUBGRAPHS / LEARNING ENGINE

Les subgraphs représentent des workflows/capacités.

Le Learning Engine reste la couche pédagogique.

Exemple :

``` text
CodingSubgraph
 ↓
evaluation
 ↓
LearningObservation
 ↓
LearningEngine
 ↓
review / practice / deepen / continue
```

Le Learning Engine ne doit pas être copié dans chaque subgraph.

------------------------------------------------------------------------

# 7. TYPED STATES

Auditer les States actuels.

Faire évoluer vers :

``` text
MainState
ActivityState
ProblemState
CodingState
ResearchState
VideoState
LearningState
```

Uniquement si ces States sont réellement nécessaires.

Ne pas dupliquer le MainState entier dans les sous-graphes.

------------------------------------------------------------------------

# 8. SUBGRAPH CONTRACT

Chaque subgraph expose :

``` text
Input
→ workflow

Output
→ structured result
```

Exemples :

``` text
ProblemResult
CodingResult
ResearchResult
VideoResult
ActivityResult
```

Les détails internes restent privés.

------------------------------------------------------------------------

# 9. TOOL ARCHITECTURE

Il faut distinguer :

``` text
Services internes
```

de :

``` text
Tools visibles par le LLM
```

Toutes les fonctions Python ne doivent pas devenir des `@tool`.

Une fonction de ranking interne reste un service si le LLM n'a pas
besoin de l'appeler directement.

------------------------------------------------------------------------

# 10. TOOL REGISTRY

Créer ou améliorer un registre central permettant d'assembler les tools
selon :

``` text
workflow
subject
capability
permissions
environment
```

Exemple :

``` text
coding
 ├── read_code
 ├── write_code
 ├── execute_code
 ├── run_tests
 └── analyze_code
```

Ne pas donner tous les tools à tous les agents.

------------------------------------------------------------------------

# 11. GROUPES DE TOOLS

## Memory

``` text
get_memory
search_memory
save_memory
update_memory
delete_memory
deduplicate_memory
summarize_memory
```

## Learning

``` text
get_learning_profile
get_topic_progress
get_goals
record_observation
update_goal
```

## Pedagogical

``` text
create_exercise
evaluate_answer
give_hint
create_quiz
next_quiz_question
assess_understanding
start_activity
continue_activity
complete_activity
```

## Coding

``` text
create_code_activity
read_code
write_code
apply_patch
execute_code
run_tests
lint_code
analyze_code
debug_code
explain_error
generate_test
inspect_project
```

## Problem

``` text
parse_problem
get_current_step
submit_step
evaluate_step
request_problem_hint
validate_problem
create_problem_artifact
```

## Research

``` text
search_web
search_source
extract_source
extract_claims
compare_sources
verify_claim
save_research
load_research
```

## Documents

``` text
list_documents
get_document
search_document
search_user_knowledge
```

## Video

``` text
get_video
transcribe_video
segment_video
search_video_segments
jump_to_timestamp
```

## MCP

Les tools sont chargés dynamiquement depuis des MCP servers autorisés.

------------------------------------------------------------------------

# 12. PEDAGOGICAL TOOLS --- AUDIT ET AMÉLIORATION

Pour chaque tool existant, vérifier :

``` text
Pydantic input
Pydantic output
description LLM
errors
authorization
user_id
thread_id
activity_id
subject
topic
idempotency
observability
```

Les tools doivent retourner des résultats structurés.

Exemple :

``` python
class ActivityToolResult(BaseModel):
    success: bool
    activity_id: str | None
    status: str
    data: dict
    error: str | None = None
```

------------------------------------------------------------------------

# 13. MEMORY TOOLS --- AUDIT ET AMÉLIORATION

Séparer absolument :

``` text
Thread State
User Memory
Learning Profile
Research Memory
Document Knowledge
```

Les tools mémoire doivent respecter :

``` text
user_id isolation
namespace
deduplication
relevance
privacy
audit
```

Préparer une recherche sémantique sur le Store persistant sans remplacer
automatiquement celui-ci par `InMemoryStore`.

`InMemoryStore` peut être utilisé pour tests/prototypes.

------------------------------------------------------------------------

# 14. ACTIVITY SYSTEM

Les activités deviennent un domaine de première classe.

Types :

``` text
exercise
quiz
code
problem
review
evaluation
video
```

Lifecycle :

``` text
created
 ↓
ready
 ↓
in_progress
 ↓
waiting_for_answer
 ↓
evaluating
 ↓
feedback
 ↓
completed
```

Erreurs :

``` text
failed
cancelled
expired
```

Utiliser le système V5.2 existant comme base.

Ne pas créer une deuxième Activity State Machine.

------------------------------------------------------------------------

# 15. ACTIVITY CONTRACT

Chaque activité doit avoir, selon le modèle existant :

``` text
activity_id
thread_id
user_id
type
subject
topic
status
created_at
updated_at
payload
attempt_count
current_step
result
```

Les champs exacts doivent être alignés sur le dépôt.

------------------------------------------------------------------------

# 16. ACTIVITY CONTINUATION

Si une activité est active :

``` text
User
 ↓
Router
 ↓
Activity continuation
 ↓
Evaluate / Guide
 ↓
Observation
 ↓
Learning Engine
 ↓
Next action
```

Ne jamais créer une nouvelle activité simplement parce que l'utilisateur
envoie une réponse à l'activité courante.

------------------------------------------------------------------------

# 17. ACTIVITY RESUME

Une activité doit pouvoir être reprise après interruption.

Utiliser :

``` text
thread_id
checkpointer
activity persistence
activity_id
```

Le frontend ne doit pas être la source de vérité.

------------------------------------------------------------------------

# 18. EVALUATION ENGINE

Séparer :

``` text
Answer
 ↓
Evaluation Engine
 ↓
EvaluationResult
 ↓
LearningObservation
 ↓
Profile Updater
 ↓
Learning Engine
```

Ne pas mélanger scoring et mise à jour du profil.

------------------------------------------------------------------------

# 19. EVALUATION STRATEGY

Priorité :

``` text
déterministe
 ↓
tests/exécution
 ↓
règles domaine
 ↓
LLM evaluation
```

Le LLM ne doit pas décider seul d'une correction lorsque des preuves
déterministes existent.

Pour le code :

``` text
tests
lint
runtime
static analysis
LLM feedback
```

sont des dimensions distinctes.

------------------------------------------------------------------------

# 20. EVALUATION RESULT

Créer ou adapter un schéma :

``` python
class EvaluationResult(BaseModel):
    activity_id: str
    score: float | None
    verdict: str
    strengths: list[str]
    weaknesses: list[str]
    feedback: str
    evidence: list[dict]
    confidence: float
```

Ne pas exposer les détails internes du scoring.

------------------------------------------------------------------------

# 21. PROBLEM SUBGRAPH

Migrer les fichiers existants vers :

``` text
graph/subgraphs/problem/
```

Cible :

``` text
START
 ↓
parse
 ↓
plan
 ↓
guide
 ↺
evaluate_step
 ↓
validate
 ↓
artifact
 ↓
END
```

Préserver :

-   parsing ;
-   plan interne ;
-   guide pas à pas ;
-   erreurs `unite/formule/signe/methode` ;
-   score de rigueur ;
-   artefact Markdown ;
-   événements SSE.

Améliorer :

``` text
typed state
structured output
retry policy
error classification
evaluation evidence
activity persistence
AgentResponse
```

------------------------------------------------------------------------

# 22. CODING SUBGRAPH

Créer :

``` text
graph/subgraphs/coding/
```

Architecture :

``` text
START
 ↓
analyze_task
 ↓
prepare_workspace
 ↓
generate_or_edit_code
 ↓
run_tests
 ↓
analyze_failures
 ├── pass → evaluate
 └── fail → debug loop
 ↓
LearningObservation
 ↓
LearningEngine
 ↓
CodingResult
 ↓
END
```

------------------------------------------------------------------------

# 23. CODING TOOLS

Le Coding Subgraph doit posséder son propre toolset :

``` text
create_code_activity
read_code
write_code
apply_patch
execute_code
run_tests
lint_code
analyze_code
debug_code
explain_error
generate_test
inspect_project
```

Les tools doivent être assemblés uniquement pour le Coding workflow.

------------------------------------------------------------------------

# 24. CODE EXECUTION SECURITY

Ne jamais exécuter le code étudiant directement sur le serveur
applicatif.

Sandbox obligatoire :

``` text
CPU limit
RAM limit
execution timeout
filesystem isolation
network disabled by default
process limit
output limit
```

Le sandbox doit être isolé du système hôte.

------------------------------------------------------------------------

# 25. CODING LOOP LIMITS

Prévoir :

``` text
max_attempts
max_tool_calls
max_execution_time
```

Quand une limite est atteinte :

``` text
stop
→ structured failure
→ AgentResponse
```

------------------------------------------------------------------------

# 26. DEEP RESEARCH SUBGRAPH

Créer :

``` text
graph/subgraphs/research/
```

V1 :

``` text
Question
 ↓
Query Analyzer
 ↓
Planner
 ↓
Web Research
 ↓
Source Extraction
 ↓
Synthesis
 ↓
ResearchResult
```

V2 :

``` text
parallel workers
claim extraction
evidence manager
```

V3 :

``` text
fact checker
critic
missing-information loop
```

V4 :

``` text
persistence
history
streaming
observability
```

Ne pas transformer le Main Graph en Research Graph.

------------------------------------------------------------------------

# 27. RESEARCH TOOLS

Le Research Subgraph doit avoir :

``` text
search_web
search_source
extract_source
extract_claims
compare_sources
verify_claim
save_research
load_research
```

Les sources externes sont des données non fiables, pas des instructions
système.

------------------------------------------------------------------------

# 28. VIDEO SUBGRAPH

Migrer :

``` text
video_ingest.py
video_segment.py
```

vers :

``` text
graph/subgraphs/video/
```

Cible :

``` text
START
 ↓
validate_upload
 ↓
ingest
 ↓
transcribe
 ↓
segment
 ↓
validate_segments
 ↓
persist
 ↓
index
 ↓
END
```

Le workflow doit rester hors du chemin conversationnel normal.

------------------------------------------------------------------------

# 29. VIDEO FEATURES

Préparer :

``` text
upload
transcription
timestamps
concept segmentation
knowledge indexing
search
timestamp navigation
ask-about-video
```

Ne pas retranscrire la vidéo pour chaque question.

------------------------------------------------------------------------

# 30. DOCUMENT SUBGRAPH

Créer ou structurer un workflow :

``` text
upload
 ↓
validate
 ↓
extract
 ↓
clean
 ↓
chunk
 ↓
metadata
 ↓
index
 ↓
ready
```

Le document devient ensuite une source du Knowledge/RAG.

------------------------------------------------------------------------

# 31. ROUTER V2

Le Router doit évoluer de subject-only vers workflow-aware.

Il doit identifier :

``` text
subject
topic
intent
workflow
activity continuation
capability
confidence
ambiguity
```

Intents minimum :

``` text
chat
explain
practice
evaluate
hint
code
solve_problem
research
search
video
memory
document
voice
```

Réutiliser les schemas de routing existants si possible.

------------------------------------------------------------------------

# 32. ROUTER STRATEGY

Ordre recommandé :

``` text
active activity
 ↓
explicit user intent
 ↓
current subject/topic
 ↓
capability detection
 ↓
deterministic rules
 ↓
LLM classifier only when necessary
```

Ne pas envoyer chaque message à un LLM de routing si une règle
déterministe suffit.

------------------------------------------------------------------------

# 33. CONTEXT BUILDER

Le Context Builder doit intégrer :

``` text
runtime context
thread state
activity
learning profile
memory
subject
topic
knowledge
search
workflow result
model capabilities
```

Un seul système de contexte principal.

------------------------------------------------------------------------

# 34. LEARNING ENGINE

Le Learning Engine reste :

``` text
deterministic
testable
explainable
```

Entrée :

``` text
BuiltContext
```

Sortie :

``` text
LearningDecision
```

Il ne doit pas appeler :

``` text
search
tools
MCP
LiveKit
database writes
```

directement.

------------------------------------------------------------------------

# 35. LEARNING ENGINE + WORKFLOWS

Exemples :

``` text
Coding
→ continue / evaluate / review / practice / deepen

Problem
→ continue / evaluate / hint / review

Video
→ explain / quiz / review

Research
→ answer / explain / deepen
```

Le moteur reste unique.

------------------------------------------------------------------------

# 36. LIVEKIT ARCHITECTURE

LiveKit doit être séparé du Main Graph :

``` text
React
 ↓
LiveKit WebRTC Room
 ↓
LiveKit Agent
 ↓
Shared services / tools
 ↓
Learning / Activity / Memory
```

LiveKit gère :

``` text
audio
voice
video
WebRTC
interruptions
turn detection
session
frontend RPC
```

LangGraph gère les workflows durables.

------------------------------------------------------------------------

# 37. LIVEKIT V1

Implémenter d'abord :

``` text
join room
 ↓
microphone
 ↓
STT/realtime model
 ↓
agent
 ↓
TTS
 ↓
leave
```

Puis ajouter :

``` text
camera
screen sharing
video understanding
frontend RPC
```

Ne pas implémenter tout en une seule étape.

------------------------------------------------------------------------

# 38. LIVEKIT SHARED TOOLS

Réutiliser les services du projet.

Ne pas créer une deuxième version de :

``` text
memory
learning
activities
coding
research
```

pour la voix.

------------------------------------------------------------------------

# 39. MCP ARCHITECTURE

MCP est une frontière d'intégration :

``` text
MCP Server
 ↓
MCP Client/Toolset
 ↓
Workflow / Agent
```

Créer un registry :

``` text
MCP server
capabilities
permissions
allowed workflows
```

------------------------------------------------------------------------

# 40. MCP TOOL SCOPING

Exemples :

``` text
CodingSubgraph
→ coding MCP tools

ResearchSubgraph
→ research MCP tools

Calendar workflow
→ calendar MCP tools
```

Ne pas exposer tous les MCP tools au Main Agent.

------------------------------------------------------------------------

# 41. MCP SECURITY

Pour chaque MCP server :

``` text
allowlist
authentication
authorization
timeouts
rate limits
audit
tool filtering
failure isolation
```

Les actions sensibles peuvent nécessiter confirmation/HITL.

------------------------------------------------------------------------

# 42. GUARDRAILS

Créer une couche :

``` text
app/guardrails/
```

Possibles :

``` text
input
tool
activity
learning
output
research
coding
```

Ne créer que les modules réellement justifiés.

------------------------------------------------------------------------

# 43. INPUT GUARDRAILS

Vérifier :

``` text
payload size
validation
authorization
rate limit
prompt injection indicators
unsupported content
dangerous tool intent
```

Ne pas dépendre uniquement de filtres par mots-clés.

------------------------------------------------------------------------

# 44. TOOL GUARDRAILS

Avant exécution :

``` text
identity
permission
scope
arguments
risk
rate limit
confirmation
```

Après :

``` text
result validation
secret filtering
size limit
```

------------------------------------------------------------------------

# 45. ACTIVITY GUARDRAILS

Vérifier :

``` text
ownership
thread
activity
transition
attempt limits
time limits
```

------------------------------------------------------------------------

# 46. LEARNING GUARDRAILS

Valider :

``` text
action
subject/topic
activity state
knowledge availability
confidence
```

Ne jamais accepter une décision qui invente une connaissance absente.

------------------------------------------------------------------------

# 47. RESPONSE GUARDRAILS

Valider :

``` text
AgentResponse schema
type
status
actions
metadata
secrets
internal fields
```

Ne jamais exposer :

``` text
system prompt
hidden answer
raw traceback
private memory
internal scores
credentials
```

------------------------------------------------------------------------

# 48. ADMIN PAGE

Créer une interface Admin protégée côté backend.

Sections possibles :

``` text
Dashboard
Users
Threads
Activities
Learning Profiles
Memory
Documents
Videos
Research
Tools
MCP
LiveKit
Logs
Errors
Models
System Health
Feature Flags
```

Ne montrer que les données réellement disponibles.

------------------------------------------------------------------------

# 49. ADMIN SECURITY

Le frontend ne doit jamais être la seule protection.

Backend :

``` text
role
permission
resource scope
```

Doit être vérifié sur chaque endpoint admin.

------------------------------------------------------------------------

# 50. ADMIN DASHBOARD

Afficher seulement des métriques réellement instrumentées :

``` text
active users
threads
activities
errors
tool calls
research jobs
video jobs
model health
database health
```

------------------------------------------------------------------------

# 51. FRONTEND MAPPING

Créer une matrice :

``` text
Feature
Backend API
Graph Node/Subgraph
Tool
AgentResponse
SSE Event
Frontend Page
Frontend Component
Admin View
Tests
```

Chaque nouvelle fonctionnalité doit être traçable de bout en bout.

------------------------------------------------------------------------

# 52. FRONTEND CARDS À AUDITER

Mettre à jour les composants existants :

``` text
ResponseRenderer
TextResponse
ExerciseCard
QuizCard
EvaluationCard
HintCard
CodeActivityCard
SearchResultCard
ClarificationCard
ErrorCard
LearningProfileCard
ContextInspectorCard
ActivityFeed
DocumentCard
VideoCard
ResearchCard
```

Ne pas créer des doublons.

------------------------------------------------------------------------

# 53. ASSISTANT UI

Utiliser Assistant UI comme surface conversationnelle principale.

Supporter selon les capacités du backend :

``` text
streaming
attachments
tool events
activities
code
documents
video
research
voice entry point
```

Le frontend consomme `AgentResponse` et les événements publics.

Il ne dépend pas de LangGraph internals.

------------------------------------------------------------------------

# 54. ATTACHMENTS

Auditer l'implémentation actuelle.

Préparer :

``` text
text
code
PDF
image
video
```

avec :

``` text
id
mime
size
upload state
processing state
owner
```

Ne jamais déduire le subject uniquement du filename.

------------------------------------------------------------------------

# 55. FRONTEND CODING

Prévoir :

``` text
CodeEditor
Run
Test
Lint
Output
Errors
Evaluation
Hint
Retry
Activity state
```

Réutiliser les composants existants.

------------------------------------------------------------------------

# 56. FRONTEND PROBLEM

Prévoir :

``` text
problem
current step
answer
evaluation
hint
progress
final result
artifact
```

Ne pas afficher le plan interne attendu.

------------------------------------------------------------------------

# 57. FRONTEND VIDEO

Prévoir :

``` text
upload
processing status
transcript
concept timeline
timestamp navigation
search
ask about video
```

------------------------------------------------------------------------

# 58. FRONTEND RESEARCH

Prévoir :

``` text
research status
queries
sources
claims
evidence
final report
citations
```

Séparer UX étudiant et diagnostic développeur.

------------------------------------------------------------------------

# 59. FRONTEND LIVEKIT

Prévoir :

``` text
voice button
room state
mic
camera
screen share
speaking indicator
mute
leave
connection errors
```

------------------------------------------------------------------------

# 60. FRONTEND ADMIN

Créer les pages nécessaires sans créer un second design system.

Réutiliser le kit UI existant.

------------------------------------------------------------------------

# 61. PRODUCTION PREPARATION

Audit obligatoire :

``` text
environment
secrets
authentication
authorization
database
migrations
backups
logging
observability
rate limits
timeouts
retries
background jobs
uploads
storage
sandbox
CORS
health checks
readiness
graceful shutdown
dependency pinning
CI
```

------------------------------------------------------------------------

# 62. HEALTH

Préparer si absent :

``` text
/health
/ready
```

Ne jamais exposer de secrets.

------------------------------------------------------------------------

# 63. ERROR TAXONOMY

Distinguer :

``` text
validation_error
user_error
authorization_error
not_found
tool_error
provider_error
timeout
rate_limit
internal_error
```

Les détails techniques restent dans les logs.

------------------------------------------------------------------------

# 64. RETRIES

Retry uniquement les erreurs transitoires :

``` text
network
provider rate limit
temporary unavailable
```

Pas de retry automatique pour :

``` text
invalid input
authorization
deterministic validation
```

------------------------------------------------------------------------

# 65. TIMEOUTS

Toutes les dépendances externes doivent avoir un timeout :

``` text
LLM
Web
MCP
LiveKit integrations
transcription
code execution
database
```

------------------------------------------------------------------------

# 66. BACKGROUND WORK

Les workflows longs doivent être découplés des requêtes HTTP synchrones.

Candidats :

``` text
video ingestion
deep research
large document ingestion
long coding jobs
```

Utiliser l'infrastructure réellement disponible dans le projet.

------------------------------------------------------------------------

# 67. IDEMPOTENCY

Ajouter si nécessaire :

``` text
activity creation
answer submission
document ingestion
video ingestion
research creation
mutating tools
```

------------------------------------------------------------------------

# 68. OBSERVABILITY

Standardiser les événements :

``` text
RUN_START
RUN_END
NODE_START
NODE_END
TOOL_START
TOOL_END
ACTIVITY_START
ACTIVITY_END
LEARNING_DECISION
RESEARCH_START
RESEARCH_END
VIDEO_START
VIDEO_END
CODE_EXECUTION_START
CODE_EXECUTION_END
MCP_TOOL_START
MCP_TOOL_END
LIVEKIT_SESSION_START
LIVEKIT_SESSION_END
ERROR
```

Toujours utiliser les correlation IDs existants.

------------------------------------------------------------------------

# 69. LOGGING

Interdit :

``` text
API keys
tokens
passwords
credentials
system prompt
full private memory
raw sensitive documents
```

Les logs doivent être structurés.

------------------------------------------------------------------------

# 70. STORE ARCHITECTURE

Conserver la séparation :

``` text
Checkpointer
→ thread state

Persistent Store
→ user memory / learning profile

RagStore
→ user documents

Activity Store
→ activity lifecycle

Research Store
→ research artifacts si justifié
```

Ne pas créer plusieurs sources de vérité.

------------------------------------------------------------------------

# 71. KNOWLEDGE INGESTION

Documents :

``` text
upload
→ extraction
→ clean
→ chunk
→ metadata
→ index
```

Videos :

``` text
upload
→ transcription
→ segmentation
→ metadata
→ index
```

Le Knowledge Store devient une source de retrieval.

------------------------------------------------------------------------

# 72. METADATA

Préserver quand disponible :

``` text
user_id
subject_id
topic
source_type
filename
document_id
video_id
timestamp
created_at
```

------------------------------------------------------------------------

# 73. DEEP RESEARCH VS NORMAL RETRIEVAL

Ne pas lancer Deep Research pour chaque question.

``` text
normal question
→ normal retrieval

deep research request
→ ResearchSubgraph
```

Le Router/Workflow Router doit déterminer le mode.

------------------------------------------------------------------------

# 74. CAS D'USAGE DU MAIN GRAPH

## Cas A --- Tutor normal

``` text
Router
→ Context
→ Learning
→ Agent
→ Response
```

## Cas B --- Activity

``` text
Router
→ Activity continuation
→ Evaluation
→ Observation
→ Learning
→ Response
```

## Cas C --- Problem

``` text
Router
→ ProblemSubgraph
→ Learning
→ Response
```

## Cas D --- Coding

``` text
Router
→ CodingSubgraph
→ Learning
→ Response
```

## Cas E --- Research

``` text
Router
→ ResearchSubgraph
→ Learning/context
→ Response
```

## Cas F --- Video ingestion

``` text
API
→ VideoSubgraph
→ Knowledge
```

Hors chemin chat normal.

## Cas G --- Voice

``` text
LiveKit
→ realtime agent
→ shared services/tools
→ Learning/Activity
```

------------------------------------------------------------------------

# 75. EVALUATION ET OPTIMISATION

Créer un dataset de tests couvrant :

``` text
routing
learning decisions
tool selection
answer quality
activity continuity
problem solving
coding correctness
research quality
memory relevance
```

Metrics :

``` text
route accuracy
decision agreement
tool success rate
evaluation agreement
retrieval relevance
citation correctness
activity completion
latency
error rate
```

Optimiser le système complet, pas uniquement le LLM.

------------------------------------------------------------------------

# 76. TESTS PAR FONCTIONNALITÉ

Chaque fonctionnalité doit avoir :

``` text
unit tests
integration tests
security tests
E2E tests
frontend tests
regression tests
```

------------------------------------------------------------------------

# 77. MATRICE GLOBALE DE TEST

Minimum :

``` text
architecture
state
router
retrieval
fallback
context
learning
activities
pedagogical tools
memory tools
problem
coding
research
video
documents
MCP
LiveKit
guardrails
AgentResponse
SSE
frontend
admin
auth
authorization
production
```

------------------------------------------------------------------------

# 78. SECURITY TESTS

Tester :

``` text
cross-user memory
cross-user documents
cross-thread activity
unauthorized admin
unauthorized tool
unauthorized MCP
code sandbox escape
oversized uploads
malicious files
prompt injection from document
prompt injection from webpage
rate limit
timeouts
```

------------------------------------------------------------------------

# 79. PERFORMANCE TESTS

Mesurer :

``` text
router latency
context latency
learning latency
tool latency
subgraph latency
research duration
video duration
code execution duration
SSE latency
LiveKit connection latency
```

Mesurer avant optimisation.

------------------------------------------------------------------------

# 80. IMPLEMENTATION PROMPT --- FORMAT OBLIGATOIRE

Pour chaque phase d'implémentation, le prompt de travail doit contenir :

``` text
MISSION
OBJECTIVE
CURRENT STATE
AUDIT
OFFICIAL DOCS
FILES TO READ
FILES TO MODIFY
FILES TO CREATE
FILES FORBIDDEN
ARCHITECTURE
IMPLEMENTATION STEPS
ERROR HANDLING
SECURITY
OBSERVABILITY
FRONTEND
TESTS
REGRESSION
DOCUMENTATION
DEFINITION OF DONE
FINAL REPORT
```

L'agent doit :

``` text
AUDIT
→ PLAN
→ IMPLEMENT
→ TEST
→ DOCUMENT
```

------------------------------------------------------------------------

# 81. TEST PROMPT --- FORMAT OBLIGATOIRE

Pour chaque phase :

``` text
Read implementation report
Read changed files
Verify architecture
Run unit tests
Run integration tests
Run security tests
Run E2E
Run frontend tests
Run regression
Check duplicates
Check permissions
Check logs
Check edge cases
Report exact results
```

Par défaut, le test agent ne modifie pas le code.

------------------------------------------------------------------------

# 82. FINAL REPORT

Créer :

``` text
RAPPORT-IMPLEMENTATION-COMPLETE.md
```

Sections :

``` text
1. Executive Summary
2. Baseline
3. Architecture Before
4. Architecture After
5. Main Graph
6. Subgraphs
7. Tools
8. Activities
9. Learning Engine
10. Evaluation
11. Memory
12. Router
13. Problem
14. Coding
15. Research
16. Video
17. Documents
18. LiveKit
19. MCP
20. Guardrails
21. Admin
22. Frontend
23. API
24. SSE
25. Security
26. Production
27. Tests
28. Performance
29. Known Limitations
30. Remaining Roadmap
31. Actual Project Tree
```

Les résultats doivent être chiffrés.

Ne jamais écrire `tests pass` sans nombre.

------------------------------------------------------------------------

# 83. PROJECT STRUCTURE TARGET

Direction cible :

``` text
backend/app/
├── graph/
│   ├── main.py
│   ├── state.py
│   ├── nodes/
│   │   ├── intake.py
│   │   ├── router.py
│   │   ├── context.py
│   │   ├── learning.py
│   │   ├── agent.py
│   │   └── response.py
│   └── subgraphs/
│       ├── problem/
│       ├── coding/
│       ├── research/
│       ├── activity/
│       ├── video/
│       └── document/
│
├── agent/
│   ├── tools/
│   │   ├── memory/
│   │   ├── pedagogical/
│   │   ├── coding/
│   │   ├── research/
│   │   └── documents/
│   └── middleware/
│
├── learning/
├── context/
├── memory/
├── activity/
├── rag/
├── knowledge/
├── evaluation/
├── guardrails/
├── mcp/
├── livekit/
├── services/
├── schemas/
├── api/
└── config/
```

Cette structure est une cible. Ne pas déplacer mécaniquement tous les
fichiers sans analyser leurs imports.

------------------------------------------------------------------------

# 84. FRONTEND TARGET

Adapter à la structure réelle :

``` text
frontend/src/
├── pages/
│   ├── chat/
│   ├── activities/
│   ├── documents/
│   ├── videos/
│   ├── research/
│   └── admin/
├── components/
│   ├── agent/
│   ├── activities/
│   ├── coding/
│   ├── problem/
│   ├── video/
│   ├── research/
│   ├── memory/
│   ├── admin/
│   └── shared/
├── api/
├── hooks/
├── stores/
├── types/
└── lib/
```

------------------------------------------------------------------------

# 85. ORDRE D'IMPLEMENTATION

Ne pas tout implémenter dans un seul changement.

## Phase 0

Audit complet.

## Phase 1

Main Graph + typed states + subgraph contracts.

## Phase 2

Activity + Evaluation.

## Phase 3

Problem Subgraph.

## Phase 4

Coding Subgraph + sandbox.

## Phase 5

Learning Engine integration.

## Phase 6

Research Subgraph.

## Phase 7

Video Subgraph.

## Phase 8

Memory tools + semantic Store.

## Phase 9

MCP.

## Phase 10

Guardrails.

## Phase 11

LiveKit voice vertical slice.

## Phase 12

LiveKit video.

## Phase 13

Admin.

## Phase 14

Frontend complete mapping.

## Phase 15

Production hardening.

## Phase 16

Full validation.

------------------------------------------------------------------------

# 86. DEFINITION OF DONE

La mission complète est terminée uniquement si :

``` text
Main StateGraph
+
typed states
+
specialized subgraphs
+
specialized toolsets
+
activities
+
evaluation
+
Learning Engine
+
memory
+
router
+
problem
+
coding
+
research
+
video
+
documents
+
MCP
+
LiveKit
+
guardrails
+
admin
+
Assistant UI
+
production hardening
```

sont intégrés sans créer de systèmes concurrents.

------------------------------------------------------------------------

# 87. RÈGLE FINALE

Avant de créer un nouveau module, répondre :

``` text
Est-ce du State ?
Est-ce du Store ?
Est-ce du Context ?
Est-ce de l'Orchestration ?
Est-ce une capacité ?
Est-ce un Tool ?
Est-ce une décision métier ?
Est-ce une représentation API ?
Est-ce du realtime ?
Est-ce une intégration externe ?
Est-ce une règle de sécurité ?
```

Si la réponse n'est pas claire, arrêter l'implémentation et résoudre le
rôle architectural.

------------------------------------------------------------------------

# 88. ARCHITECTURE CIBLE FINALE

``` text
                              USER
                                │
                                ▼
                             FastAPI
                                │
                                ▼
                         ┌──────────────┐
                         │  Main Graph  │
                         └──────┬───────┘
                                │
                              Router
                                │
                         Workflow Router
                                │
        ┌───────────────────────┼────────────────────────┐
        │                       │                        │
        ▼                       ▼                        ▼
    Problem                  Coding                  Research
   Subgraph                 Subgraph                 Subgraph
        │                       │                        │
        └───────────────────────┼────────────────────────┘
                                │
                             Context
                                │
                         Learning Engine
                                │
                              Agent
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
                Tools          MCP         Knowledge
                  │             │             │
                  └─────────────┼─────────────┘
                                ▼
                         Response Node
                                │
                                ▼
                         AgentResponse
                                │
                                ▼
                             Frontend
```

Workflows longs :

``` text
Video Upload → VideoSubgraph → Knowledge Store
Document Upload → DocumentSubgraph → Knowledge Store
```

Realtime :

``` text
LiveKit Room
 → LiveKit Agent
 → shared domain services/tools
 → Activity / Learning / Memory
```

------------------------------------------------------------------------

# 89. PRINCIPE DIRECTEUR

Ne pas chercher à avoir le plus grand nombre de nodes.

Chercher :

``` text
clarté
durabilité
testabilité
sécurité
observabilité
réutilisation
performance
UX
```

Le projet doit rester compréhensible par un développeur qui n'a pas
écrit les premières versions.
