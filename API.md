# API — Agent Tutor

Contrats HTTP du backend. Décrit l'état réel au commit `bba8c36` (2026-09-29).

## Base URL

| Contexte | URL |
|---|---|
| Navigateur (prod) | `/api/*` — proxyé par Vercel vers `agent-tutor-api.onrender.com` |
| Direct | `https://agent-tutor-api.onrender.com/api/*` |
| Local | `http://localhost:8000/api/*` |

Le navigateur ne voit jamais le backend : **Vercel relaie et ajoute ses propres en-têtes.** C'est aujourd'hui la source du problème CORS décrit dans `DECISIONS.md` ADR-015.

## Versionnement

**Aucun.** Les routes sont plates (`/api/users`, `/api/threads/...`). Un changement de contrat est donc un changement cassant — ce qui est acceptable tant qu'il n'y a pas de client tiers, et ne le sera plus le jour où il y en aura un. Décision à prendre avant, pas après.

Documentation interactive : `/docs` (Swagger) et `/redoc`, servis par FastAPI.

## Authentification

**Toutes les routes sauf celles listées en « Public » exigent un Bearer token.**

```
Authorization: Bearer <jwt>
```

| Mode | Format attendu |
|---|---|
| `AUTH_MODE=neon` (prod) | JWT signé par Neon Auth, vérifié via JWKS |
| `AUTH_MODE=dev` | `Bearer dev:<nom>` — crée/provisionne un utilisateur au premier appel |
| autre valeur | **503 sur toutes les routes authentifiées** |

Résolution : le claim `sub` → `users.clerk_user_id` → `user_id` interne. Si l'utilisateur n'existe pas encore, il est **provisionné automatiquement** au premier login.

### Public

Ces routes ne demandent **aucun** token :

| Route | Raison |
|---|---|
| `GET /` | informative |
| `GET /api/health`, `/ready`, `/model-gateway`, `/langsmith`, `/auth` | sondes de santé — doivent répondre même si l'auth est cassée |
| `GET /api/models` | catalogue de modèles, lu par le sélecteur avant l'authentification |
| `GET /api/subjects`, `GET /api/subjects/{id}`, `GET /api/subjects/{id}/topics` | référentiel public |
| `POST /api/users` | **uniquement en `AUTH_MODE=dev`** — la route est déclarée à l'intérieur d'un `if AUTH_MODE == "dev":` (`api/users.py:90-108`) et n'existe pas en production |

## Format des erreurs

Toutes les erreurs — métier, de validation ou inattendue — ont la même forme :

```json
{
  "detail": "message lisible, sans secret",
  "code": "taxon court et stable",
  "error": true
}
```

`detail` est **sanitisé** : la cause technique est tronquée à 300 caractères (`app/core/exceptions.py:51`). Un client peut donc afficher `detail` tel quel.

`code` est le seul élément stable pour un client : s'y accrocher plutôt qu'à `detail`.

| Situation | Statut | Origine |
|---|---|---|
| Erreur métier `AppError` | `exc.status_code` (500 par défaut) | `app/core/exceptions.py:34` |
| Validation, autorisation, not found | 4xx explicite | `HTTPException` dans la route |
| Exception non gérée | **500**, `code: "unhandled_error"`, **jamais de stack trace** | `app/main.py` `@app.exception_handler(Exception)` |
| Ressource qui n'appartient pas à l'utilisateur | **403** | contrôle d'ownership dans la route |

## CORS

`app/main.py:109` installe un `CORSMiddleware` paramétré par `ALLOWED_ORIGINS`.

> ⚠ **Défaut actuel** : `vercel.json` déclare `Access-Control-Allow-Origin: *` sur `/api/(.*)`, ce qui **court-circuite** cette protection. Correction prévue : `ROADMAP.md` lot B1.

---

## Routes par domaine

Légende : 🔓 public · 🔒 `get_current_user` · 🔑 `require_admin`

### Santé — `api/health.py`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| GET | `/api/health` | santé globale | 🔓 |
| GET | `/api/health/ready` | readiness — **503 si la base est injoignable** | 🔓 |
| GET | `/api/health/model-gateway` | état du gateway LLM | 🔓 |
| GET | `/api/health/langsmith` | connectivité LangSmith | 🔓 |
| GET | `/api/health/auth` | mode d'auth effectif | 🔓 |

### Utilisateurs — `api/users.py`, prefix `/api/users`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| GET | `/me` | utilisateur courant (dérivé du token, pas d'ID client) | 🔒 |
| POST | `` | **dev uniquement** — crée un utilisateur de test et renvoie son `dev_token` | 🔓 (dev) |
| GET | `` | lister | 🔒 admin |
| GET | `/{user_id}` | lire | 🔒 |
| GET | `/{user_id}/profile` | profil pédagogique | 🔒 |
| PUT | `/{user_id}/profile` | modifier le profil | 🔒 |
| GET | `/{user_id}/memory` | aperçu mémoire | 🔒 |
| GET | `/{user_id}/memory/facts` | faits mémorisés | 🔒 |
| GET | `/{user_id}/memories`, `/{user_id}/facts` | lecture mémoire | 🔒 |
| POST | `/{user_id}/memories` | écrire un fait | 🔒 |
| PUT | `/{user_id}/memories/{memory_id}` | modifier | 🔒 |
| DELETE | `/{user_id}/memories/{memory_id}` | supprimer | 🔒 |

**Règle** : `user_id` dans le chemin est **toujours** comparé à l'identité du token. Un `user_id` différent renvoie 403, pas les données.

### Fil de discussion — `api/threads.py`, prefix `/api`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| POST | `/users/{user_id}/threads` | créer | 🔒 |
| GET | `/users/{user_id}/threads` | lister | 🔒 |
| GET | `/threads/{thread_id}` | lire | 🔒 |
| PUT | `/threads/{thread_id}` | renommer / modifier | 🔒 |
| DELETE | `/threads/{thread_id}` | supprimer — **204** | 🔒 |

### Chat et streaming — `api/chat.py`, prefix `/api/chat`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| POST | `` | tour de conversation complet → `ChatResponse` | 🔒 |
| GET | `/stream` | même chose en **SSE** | 🔒 |

Les événements SSE sont **sanitisés** : un message d'erreur brut n'est jamais poussé au client. Un `workflow_result` peut être streamé (voir `MEMORY.md`, section refactor V10).

### Mémoire liée au fil — `api/memory.py`, prefix `/api/threads`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| GET | `/{thread_id}/state` | état LangGraph du fil | 🔒 |
| GET | `/{thread_id}` | résumé mémoire du fil | 🔒 |

### Activité — `api/activity.py`, prefix `/api/threads`

| Méthode | Route | Accès |
|---|---|---|
| GET | `/{thread_id}/activity` | 🔒 |
| POST | `/{thread_id}/activity` | 🔒 |

### Apprentissage — `api/learning.py`, prefix `/api/learning`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| GET | `/{user_id}/profile` | profil apprenant | 🔒 |
| GET | `/{user_id}/observations` | observations | 🔒 |
| GET | `/{user_id}/topics` | sujets couverts | 🔒 |
| GET | `/{user_id}/{subject}/{topic}` | détail sujet/topic | 🔒 |
| GET | `/{user_id}/goals` | objectifs | 🔒 |

### Documents (RAG) — `api/documents.py`, prefix `/api/users`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| POST | `/{user_id}/documents` | ingérer (upload + vectorisation) | 🔒 |
| GET | `/{user_id}/documents` | lister | 🔒 |
| GET | `/{user_id}/documents/{doc_id}` | lire | 🔒 |
| DELETE | `/{user_id}/documents/{doc_id}` | supprimer | 🔒 |

### Stockage objet — `api/storage.py`, prefix `/api`

| Méthode | Route | Accès |
|---|---|---|
| POST | `/users/{user_id}/storage/{kind}` | 🔒 |
| GET | `/users/{user_id}/storage` | 🔒 |
| GET | `/storage/{object_id}` | 🔒 |
| DELETE | `/storage/{object_id}` | 🔒 |

Le contenu binaire vit dans **Neon S3** ; la base ne stocke que les métadonnées.

### Matières — `api/subjects.py`, prefix `/api/subjects`

| Méthode | Route | Accès |
|---|---|---|
| GET | `` | 🔓 |
| GET | `/{subject_id}` | 🔓 |
| GET | `/{subject_id}/topics` | 🔓 |
| POST | `` | 🔒 |

### Contexte — `api/context.py`, prefix `/api/context`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| POST | `/preview` | prévisualiser le contexte assemblé sans consommer de LLM | 🔒 |

### Modèles — `api/models.py`, prefix `/api/models`

| Méthode | Route | Accès |
|---|---|---|
| GET | `` | 🔓 |

### Voix / vidéo — `api/livekit.py`, prefix `/api/livekit`

| Méthode | Route | Rôle | Accès |
|---|---|---|---|
| POST | `/token` | token de connexion à la salle | 🔒 |
| POST | `/verify` | vérifier la configuration de la session | 🔒 |
| POST | `/agent/start` | démarrer l'agent vocal | 🔒 |
| GET | `/agent/status` | état de l'agent | 🔒 |
| POST | `/agent/stop` | arrêter l'agent | 🔒 |
| GET | `/screen-share/status` | état du partage d'écran | 🔒 |
| POST | `/screen-share/notify` | notifier un changement d'écran | 🔒 |

> Le partage d'écran est **non critique** : son échec est publié comme `screen_capture_unavailable` et la voix continue.

### Transcription — `features/transcription/api.py`

| Rôle | Accès |
|---|---|
| Transcription de fichiers audio/vidéo vers segments vectorisés | 🔒 |

### Journaux — `api/logs.py`, prefix `/api/logs`

| Méthode | Route | Accès |
|---|---|---|
| GET | `` | 🔑 |

---

## Administration — `/api/admin`

Toutes les routes de cette section exigent le rôle admin.

> ⚠ **Incohérence à corriger** (`ROADMAP.md` lot B7) : trois noms coexistent pour la même vérification.
> `require_admin` (`app/auth/resolver.py:299`) · `verify_admin_auth` (`app/api/admin/observability.py:35`, délègue à `require_admin`) · `get_current_admin_user`, qui n'est **qu'un alias importé** de `require_admin` (`app/api/admin/dashboard.py:15`).
> La sécurité n'est pas en jeu — les trois aboutissent au même contrôle — mais trois noms pour une même règle rendent l'audit inutilement difficile.

### Knowledge bases — `api/admin/knowledge.py`

| Méthode | Route | Rôle |
|---|---|---|
| GET | `` | lister les bases |
| POST | `` | créer — 201 |
| PATCH | `/{kb_id}` | modifier |
| DELETE | `/{kb_id}` | supprimer |
| GET | `/{kb_id}/access` | règles d'accès |
| POST | `/{kb_id}/access` | ajouter une règle |
| DELETE | `/{kb_id}/access` | retirer |
| GET | `/content` | sections |
| POST | `/content` | ajouter une section |
| DELETE | `/content/{section_id}` | supprimer |

### Modèles — `api/admin/models.py`

| Méthode | Route | Rôle |
|---|---|---|
| GET | `` | lister |
| POST | `` | créer — 201 |
| PATCH | `/{model_id}` | modifier |
| DELETE | `/{model_id}` | supprimer |
| POST | `/{model_id}/test` | tester un modèle |
| GET | `/{model_id}` | détail |

Ces routes écrivent `app/models.yaml` : **changer de modèle ne demande pas de redéploiement**.

### Matières — `api/admin/subjects.py`

| Méthode | Route |
|---|---|
| GET | `` |
| GET | `/{subject_id}/definition` |
| PUT | `/{subject_id}/definition` |
| DELETE | `/{subject_id}/definition` |

Les modifications invalident le registre des matières (`registry.invalidate()`).

### Monitoring — `api/admin/monitoring.py`

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/events` | flux d'événements bruts |
| GET | `/summary` | résumé |
| GET | `/stats` | statistiques |

### Observabilité — `api/admin/observability.py`

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/summary` | synthèse des runs |
| GET | `/runs` | lister les runs |
| GET | `/run/{run_id}` | détail d'un run |
| GET | `/evaluations` | résultats d'évaluation |
| GET | `/models/usage` | consommation par modèle |
| GET | `/errors` | erreurs agrégées |
| GET | `/langsmith-link` | lien profond LangSmith |

`/models/usage` et `/errors` répondent `UnavailableResponse` quand LangSmith est injoignable — **l'observabilité ne fait pas tomber l'API**.

### Dashboard — `api/admin/dashboard.py`, monté sous `/api/admin/dashboard`

| Méthode | Route |
|---|---|
| GET | `/metrics` |
| GET | `/activity-stats` |

### Utilisateurs — `api/admin/users.py`, monté sous `/api/admin/users`

| Méthode | Route | Rôle |
|---|---|---|
| PUT | `/{user_id}/role` | changer le rôle (body `{role: "admin"\|"user"}`) |

Canal d'écriture explicite du rôle (ADR-023) : `users.role` en base est l'autorité unique au runtime ; cette route remplace l'auto-persistance d'écart retirée du resolver. **Anti-lockout** : un admin ne peut pas modifier son propre rôle (422) — la modification doit venir d'un autre admin ou d'un UPDATE SQL.

---

## Points à ne pas oublier en intégration

1. **`/api/chat/stream` est un SSE, pas un JSON.** Un client qui fait un `fetch` sans `Accept: text/event-stream` ne recevra rien d'interprétabile.
2. **DELETE renvoie 204** sur `/api/threads/{id}` — pas de corps àparser.
3. **Les erreurs ont toujours la même forme**, y compris pour une 500 : `{detail, code, error: true}`. Aucun cas ne renvoie une stack trace.
4. **Les schémas de requête et de réponse sont les sources de vérité** : `api/*_schemas.py`. Ce document donne la forme des URLs, des statuts et de l'authentification — pas la définition des champs. Lire les schémas Pydantic avant d'intégrer.
