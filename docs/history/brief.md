# BRIEF — FRONTEND DE MON AGENT LANGGRAPH

## 1. Objectif

Créer une interface web moderne permettant de superviser et utiliser mon agent Python LangGraph.

Le frontend doit donner l'impression d'un véritable "Agent Control Center".

L'application doit comporter exactement 3 pages principales :

1. Chat
2. Memory
3. Logs

Le frontend doit être conçu pour fonctionner avec un backend Python/FastAPI qui expose mon agent LangGraph.

---

# 2. Stack frontend

Utiliser :

* React
* TypeScript
* Vite
* Tailwind CSS
* shadcn/ui
* Lucide React
* Framer Motion

Architecture propre et modulaire.

Ne pas mettre toute la logique dans App.tsx.

Créer des composants réutilisables.

---

# 3. Direction artistique

Style :

* interface AI developer tool
* moderne
* professionnelle
* sombre
* minimaliste
* légèrement futuriste
* beaucoup de profondeur visuelle
* cartes avec bordures fines
* animations fluides

Éviter le style "cyberpunk".

Je veux une interface proche d'un dashboard SaaS moderne destiné à des développeurs.

Palette :

Background :
#0B0F14

Surface :
#111820

Surface secondaire :
#18212B

Border :
#26323D

Texte principal :
#F5F7FA

Texte secondaire :
#94A3B8

Accent principal :
#6C63FF

Success :
#22C55E

Warning :
#F59E0B

Error :
#EF4444

---

# 4. Layout général

Créer un layout global :

┌────────────────────────────────────────────────────────────┐
│ Header                                                     │
├──────────────┬─────────────────────────────────────────────┤
│ Sidebar      │                                             │
│              │                 Main Content                │
│ Chat         │                                             │
│ Memory       │                                             │
│ Logs         │                                             │
│              │                                             │
│              │                                             │
└──────────────┴─────────────────────────────────────────────┘

Sidebar :

* logo "Agent Lab"
* Chat
* Memory
* Logs
* statut Ollama
* statut LangGraph
* statut SQLite

En bas du sidebar afficher :

"Agent Online"

avec un petit indicateur animé.

---

# 5. PAGE CHAT

Route :

/chat

C'est la page principale.

## Header

Afficher :

Agent Chat

Puis :

Model:
Qwen

Thread:
<thread_id>

User:
<user_id>

Status:
Online

---

## Zone de conversation

Afficher les messages dans des cartes distinctes.

Message utilisateur :

aligné à droite.

Message agent :

aligné à gauche.

Utiliser une animation légère lors de l'apparition d'un message.

---

# 6. VISUALISATION DES TOOLS

Cette partie est très importante.

Quand l'agent utilise un tool, afficher une animation visuelle.

Exemple :

User demande :

"Calcule 45 + 78"

Pendant l'exécution :

┌─────────────────────────────────────────────┐
│ Tool execution                              │
│                                             │
│ ⚙ additionner                              │
│                                             │
│ Input                                       │
│ a = 45                                      │
│ b = 78                                      │
│                                             │
│ ● Running...                                │
└─────────────────────────────────────────────┘

Puis transformer la carte en :

┌─────────────────────────────────────────────┐
│ ✓ additionner                              │
│                                             │
│ 45 + 78 = 123                               │
│                                             │
│ Completed in 120ms                          │
└─────────────────────────────────────────────┘

Utiliser Framer Motion pour :

* apparition
* pulse pendant l'exécution
* transition running → success
* disparition éventuelle

---

# 7. Tool status

Créer trois cartes :

additionner
calculer_longueur_texte
recherche_web

Chaque tool possède un statut :

IDLE
RUNNING
SUCCESS
ERROR

Exemple :

● additionner
SUCCESS

● recherche_web
RUNNING

● calculer_longueur_texte
IDLE

Les statuts doivent être animés.

---

# 8. PANEL D'ACTIVITÉ

Sur la droite de la page Chat, créer un panneau :

"Agent Activity"

Afficher en temps réel :

16:42:01
Agent started

16:42:02
Tool called: additionner

16:42:02
Tool completed

16:42:03
Response generated

16:42:03
Checkpoint saved

Chaque événement doit apparaître progressivement.

---

# 9. PAGE MEMORY

Route :

/memory

Objectif :

Visualiser la mémoire persistante de LangGraph.

Afficher :

User ID

Thread ID

Interaction count

Messages count

Last checkpoint

---

Créer une section :

"Current State"

Afficher les données du state dans une interface lisible.

Exemple :

User ID
550e8400...

Thread ID
thread-001

Interaction count
12

Messages
24

---

Créer aussi :

"Conversation Timeline"

Afficher chronologiquement les checkpoints.

Exemple :

Checkpoint #1
User message
"Bonjour"

↓

Checkpoint #2
Assistant response

↓

Checkpoint #3
Tool call

↓

Checkpoint #4
Assistant response

Utiliser une timeline animée.

---

# 10. PAGE LOGS

Route :

/logs

Afficher les logs du fichier backend.

Créer une interface de terminal moderne.

Exemple :

16:42:01 INFO RUN_START
16:42:01 INFO STATE_LOAD
16:42:02 INFO USER_MESSAGE
16:42:02 INFO TOOL_START
16:42:02 INFO TOOL_END
16:42:03 INFO ASSISTANT_MESSAGE
16:42:03 INFO RUN_END

Colorer visuellement :

INFO
SUCCESS
WARNING
ERROR

Ajouter :

* recherche
* filtre par niveau
* filtre par tool
* bouton pause/reprise du streaming
* bouton clear visual
* auto-scroll

---

# 11. LIVE LOG STREAM

Le frontend doit pouvoir recevoir les nouveaux logs en temps réel.

Prévoir WebSocket ou Server-Sent Events.

Architecture souhaitée :

Backend
↓
WebSocket / SSE
↓
Frontend
↓
Live Log Console

Lorsqu'un événement arrive :

le log doit apparaître avec une animation.

---

# 12. API FRONTEND

Prévoir une couche API dédiée :

src/
├── api/
│   ├── agent.ts
│   ├── memory.ts
│   └── logs.ts
│
├── components/
│   ├── chat/
│   ├── memory/
│   ├── logs/
│   ├── tools/
│   └── layout/
│
├── pages/
│   ├── ChatPage.tsx
│   ├── MemoryPage.tsx
│   └── LogsPage.tsx
│
├── hooks/
│   ├── useChat.ts
│   ├── useLogs.ts
│   └── useMemory.ts
│
└── types/
└── agent.ts

Ne pas mélanger les appels HTTP directement
dans les composants UI.

---

# 13. API backend attendue

Prévoir les endpoints :

POST /api/chat

GET /api/threads

GET /api/threads/{thread_id}

GET /api/threads/{thread_id}/state

GET /api/threads/{thread_id}/history

GET /api/logs

GET /api/health

WebSocket :

/ws/logs

---

# 14. Chat API

POST /api/chat

Request :

{
"user_id": "...",
"thread_id": "...",
"message": "..."
}

Response :

{
"response": "...",
"user_id": "...",
"thread_id": "...",
"interaction_count": 4
}

---

# 15. Thread management

Dans la page Chat ajouter :

"New Thread"

Lorsqu'on clique :

générer un nouveau thread_id UUID.

Permettre également à l'utilisateur de saisir manuellement :

User ID
Thread ID

Prévoir un sélecteur :

"Recent Threads"

avec la liste des conversations disponibles.

---

# 16. Memory API

GET /api/threads/{thread_id}/state

Retour attendu :

{
"user_id": "...",
"thread_id": "...",
"interaction_count": 5,
"messages": [...]
}

Afficher ces informations dans la page Memory.

---

# 17. Logs API

GET /api/logs

Retour :

[
{
"timestamp": "...",
"level": "INFO",
"event": "TOOL_START",
"message": "...",
"thread_id": "..."
}
]

Prévoir pagination ou limite de lignes.

---

# 18. Tool visualization architecture

Créer un composant :

<ToolExecutionCard />

Props :

toolName
status
input
output
duration

Exemple :

<ToolExecutionCard
toolName="additionner"
status="running"
input={{ a: 10, b: 20 }}
/>

Puis :

<ToolExecutionCard
toolName="additionner"
status="success"
input={{ a: 10, b: 20 }}
output={30}
duration={120}
/>

---

# 19. Animations

Utiliser Framer Motion.

Animations souhaitées :

* message fade/slide
* tool card pulse
* success check animation
* spinner
* timeline reveal
* log line reveal
* sidebar hover
* page transition légère

Les animations doivent rester professionnelles et rapides.

Pas d'animations excessives.

---

# 20. Responsive

Le dashboard doit fonctionner :

* desktop
* laptop
* tablette

Priorité :

Desktop 1440px.

---

# 21. UX

L'utilisateur doit comprendre immédiatement :

1. quel agent est actif
2. quel modèle est utilisé
3. quel thread est actif
4. quel utilisateur est actif
5. quels tools sont disponibles
6. quels tools sont en cours d'exécution
7. ce que fait actuellement l'agent
8. ce qui a été sauvegardé dans SQLite

---

# 22. IMPORTANT

Ne simule pas le fonctionnement des tools uniquement avec des animations.

Les animations doivent représenter les événements réellement reçus du backend.

Exemple :

Backend :

TOOL_START
↓
Frontend
↓
Animation RUNNING

Backend :

TOOL_END
↓
Frontend
↓
Animation SUCCESS

Même chose pour ERROR.

---

# 23. Architecture finale

Frontend :

React
TypeScript
Tailwind
shadcn
Framer Motion

Backend :

Python
FastAPI
LangGraph
LangChain
Ollama

Persistence :

SQLite
SqliteSaver

Logs :

agent.log

Realtime :

WebSocket ou SSE

Architecture :

React
│
├── Chat
├── Memory
└── Logs
│
▼
FastAPI
│
▼
LangGraph Agent
│
├── Tools
│
└── SqliteSaver
│
▼
checkpoints.db
