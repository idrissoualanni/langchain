# Documentation Technique : Système de Mémoire Cognitive

Ce document centralise la description fonctionnelle et technique de l'écosystème de mémoire cognitive.

## 1. Architecture Globale
Le système transforme l'interaction agent-utilisateur en un processus d'apprentissage structuré, où chaque donnée est vectorisée et cartographiée.

### Flux de données :
`Interaction Utilisateur` $\rightarrow$ `Analyse Cognitive (LLM)` $\rightarrow$ `CognitiveStore (Neon)` $\rightarrow$ `HybridRetriever` $\rightarrow$ `Context Builder` $\rightarrow$ `Prompt Système` $\rightarrow$ `Réponse Adaptative`.

---

## 2. Détail des Fonctionnalités par Fichier

### 📁 Backend : Services & Infrastructure
| Fichier | Responsabilités | Fonctionnalités Clés |
| :--- | :--- | :--- |
| `app/services/memory/cognitive_store.py` | **Cœur de Persistance** | - `save_memory()` : Vectorisation et stockage Neon.<br>- `retrieve_memories()` : Recherche cosinus brute.<br>- `update_concept_mastery()` : Gestion du niveau de maîtrise.<br>- `get_user_learning_graph()` : Export du graphe de savoirs. |
| `app/services/memory/hybrid_retriever.py` | **Moteur de Recherche** | - `retrieve()` : Fusion sémantique + lexicale.<br>- `_apply_mmr()` : Diversification des résultats (anti-redondance).<br>- Optimisation Batch : Récupération groupée des vecteurs. |
| `app/services/memory/memory.py` | **Facade de Service** | - `read_profile()` / `write_profile()` : Gestion de l'identité.<br>- `save_fact()` / `search_facts()` : Interface simplifiée pour l'agent. |
| `app/services/context/builder.py` | **Orchestration du Contexte** | - Injection automatique du profil utilisateur dans le contexte de chaque tour. |
| `app/services/context/prompt_builder.py` | **Génération du Prompt** | - Construction de la section "CORE PERSONA" en tête du prompt. |

### 📁 Backend : API & Tools
| Fichier | Responsabilités | Fonctionnalités Clés |
| :--- | :--- | :--- |
| `app/api/user/memory.py` | **Interface Utilisateur** | - `/api/user/memory/overview` : Vue d'ensemble profil + faits.<br>- `/api/user/memory/learning-map` : Données du graphe 3D. |
| `app/tools/memory/` | **Capacités de l'Agent** | - `update_user_identity` : Enregistrement intuitif de traits.<br>- `query_cognitive_memory` : Recherche "Sens Réel". |

### 📁 Frontend : Interface "Mon Cerveau"
| Fichier | Responsabilités | Fonctionnalités Clés |
| :--- | :--- | :--- |
| `features/user/memory/LearningMap.tsx` | **Visualisation 3D** | - Graphe de force via `@react-three/fiber`.<br>- Couleurs de maîtrise (Rouge $\rightarrow$ Vert).<br>- Navigation et détails des concepts. |
| `features/user/memory/PersonaDashboard.tsx` | **Centre de Contrôle** | - Orchestration de la map 3D et du nuage de souvenirs.<br>- Édition du profil utilisateur. |
| `features/user/memory/MemorySearchBar.tsx` | **Recherche Sémantique** | - Interface de requête directe vers le moteur hybride. |

---

## 3. Guide de Maintenance Rapide
- **Ajouter un concept** $\rightarrow$ `user_learning_map` (maîtrise) $\rightarrow$ `concept_dependencies` (liens).
- **Modifier le prompt** $\rightarrow$ `app/services/agent/prompts.py` (respecter la posture d'observateur).
- **Vérifier la base** $\rightarrow$ Console Neon $\rightarrow$ Table `user_cognitive_memories`.
