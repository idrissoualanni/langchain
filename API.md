# API.md

## 📑 Contrats d'Interface

Ce document est la source de vérité pour les endpoints de l'API. Il doit être mis à jour à chaque modification des schémas Pydantic dans `backend/app/api/`.

### 1. Authentification & Utilisateurs
| Endpoint | Méthode | Description | Schéma Request | Schéma Response |
| :--- | :--- | :--- | :--- | :--- |
| `/api/users/me` | GET | Récupère le profil de l'utilisateur actuel | - | `UserResponse` |
| `/api/user/memory/overview` | GET | Vue d'ensemble de la mémoire cognitive | - | `MemoryOverview` |
| `/api/user/memory/learning-map` | GET | Données pour le graphe 3D | - | `LearningMapData` |

### 2. Agent & Chat
| Endpoint | Méthode | Description | Schéma Request | Schéma Response |
| :--- | :--- | :--- | :--- | :--- |
| `/api/chat` | POST | Envoie un message à l'agent (SSE) | `ChatRequest` | `ChatResponse` (Stream) |
| `/api/livekit/token` | GET | Génère un jeton d'accès LiveKit | - | `LiveKitToken` |

### 3. Administration
| Endpoint | Méthode | Description | Accès | Schéma Response |
| :--- | :--- | :--- | :--- | :--- |
| `/api/admin/subjects` | GET/POST | Gestion du registre des matières | `require_admin` | `SubjectList` |
| `/api/health` | GET | État de santé du système | Public | `HealthStatus` |
