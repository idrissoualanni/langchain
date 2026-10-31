# API.md

## 📑 Contrats d'Interface

Ce document est la source de vérité pour les endpoints de l'API. Il doit être mis à jour à chaque modification des schémas Pydantic dans `backend/app/api/`.

### 1. Authentification & Utilisateurs
| Endpoint | Méthode | Description | Schéma Request | Schéma Response |
| :--- | :--- | :--- | :--- | :--- |
| `/api/users/me` | GET | Récupère le profil de l'utilisateur actuel | - | `UserResponse` |
| `/api/users/{user_id}/memory` | GET | Vue d'ensemble de la mémoire (profil + faits par catégorie). **Propriétaire uniquement, admin compris** | - | `MemoryOverviewOut` |
| `/api/users/{user_id}/memory/facts` | GET/POST | Liste (filtre `category`) / ajoute un fait. Propriétaire uniquement | `MemoryFactCreate` | `MemoryFactOut` |
| `/api/users/{user_id}/memory/facts/{fact_id}` | PUT/DELETE | Modifie / supprime un fait. Propriétaire uniquement | `MemoryFactUpdate` | `MemoryFactOut` / `{deleted}` |
| `/api/users/{user_id}/memory/search?q=` | GET | Recherche sémantique dans les faits. Propriétaire uniquement | - | `MemoryFactOut[]` |
| `/api/threads/{thread_id}/state` | GET | Historique du thread (checkpointer). Propriétaire uniquement, admin compris | - | `StateResponse` |
| `/api/user/memory/learning-map` | GET | Données pour le graphe 3D | - | `LearningMapData` |

### 2. Agent & Chat
| Endpoint | Méthode | Description | Schéma Request | Schéma Response |
| :--- | :--- | :--- | :--- | :--- |
| `/api/chat` | POST | Envoie un message à l'agent — réponse complète | `ChatRequest` | `ChatResponse` |
| `/api/chat/stream` | POST | Envoie un message — flux SSE des événements du pipeline (ex-GET : le message ne passe plus par l'URL ; requête soumise au contrôle d'Origine). `user_id` doit être celui de la session, admin compris | `ChatRequest` (corps JSON) | `text/event-stream` |
| `/api/livekit/token` | GET | Génère un jeton d'accès LiveKit | - | `LiveKitToken` |

### 3. Administration
| Endpoint | Méthode | Description | Accès | Schéma Response |
| :--- | :--- | :--- | :--- | :--- |
| `/api/admin/subjects` | GET/POST | Gestion du registre des matières | `require_admin` | `SubjectList` |
| `/api/health` | GET | État de santé du système | Public | `HealthStatus` |
