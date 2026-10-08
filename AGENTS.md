# AGENTS.md

## ⚖️ Gouvernance & Sécurité (Règles Fondamentales)

Ces règles sont opposables à tout agent et toute intervention humaine. Toute dérogation doit être validée par l'Architecte et consignée dans `DECISIONS.md`.

### 1. Sécurité des Secrets & Environnement
- **Zéro Fuite** : Un secret ne quitte jamais sa source. Aucun `echo`/`print`/log de valeur.
- **Gestion Render** : Utiliser exclusivement `scripts/devops/push-env-secret.py` pour pousser des secrets vers Render sans les afficher.
- **Isolation** : Les fichiers `.env`, `.env.local` et `.vercel/` sont strictement interdits dans le dépôt.

### 2. Gestion des Ressources & Performance (Windows/Render)
- **Bornage Git** : Pour éviter les `WinError 1455` / `malloc failed`, utiliser systématiquement :
  `git -c pack.threads=1 -c pack.deltaCacheSize=4m -c pack.windowMemory=16m push origin master`.
- **Hygiène Disque** : Purger les caches régénérables (`node_modules/.vite`, `dist`, `__pycache__`) avant tout push ou suite de tests via `.opencode/scripts/cleanup-cache.sh`.

### 3. Intégrité des Données & Base de Données
- **Source Unique** : Postgres (Neon) est la seule source de vérité. L'utilisation de SQLite est strictement réservée au développement local et interdite en staging/prod.
- **Souveraineté** : L'accès aux données de mémoire cognitive est réservé à l'utilisateur. L'administration n'a aucun droit de lecture sur ces tables.

### 4. Flux de Développement & Qualité
- **Cycle de Vie** : `api/` $\rightarrow$ `services/` $\rightarrow$ `repositories/` $\rightarrow$ `infrastructure/database/`.
- **Contrats** : Toute modification de route doit être reflétée dans `API.md`.
- **Tests** : Tout bug corrigé doit être accompagné d'un test de reproduction.

---

## 🤖 Équipe d'Experts

| Agent | Rôle | Responsabilité |
| :--- | :--- | :--- |
| **Architecte** | Vision & Structure | Design système, choix technologiques, cohérence globale. |
| **Frontend** | Interface & UX | React, Vite, Three.js, accessibilité et fluidité UI. |
| **Backend** | Logique & API | FastAPI, Orchestration LangGraph, Services métier. |
| **Sécurité** | Souveraineté & Auth | Gestion des secrets, isolation des données, audit Neon Auth. |
| **DevOps** | Infra & CI/CD | Render, Vercel, Workflows GitHub, optimisation RAM/Disk. |
| **API** | Contrats & Intégration | Spécifications OpenAPI, validation Pydantic, MCP servers. |
| **Debugging** | Qualité & Tests | Analyse de logs, tests unitaires/E2E, correction de bugs. |
| **Changelog** | Historique & Docs | Suivi des versions, documentation des fonctionnalités. |

## ⚙️ Navigation
L'architecture doit toujours pointer vers [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md).
