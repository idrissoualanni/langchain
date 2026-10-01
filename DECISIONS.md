# DECISIONS — Agent Tutor

Registre des décisions d'architecture. **Une entrée par décision, jamais modifiée après validation** : on la supersède.

Format : date · statut · contexte · options · décision · conséquences · **revu si**.

Statuts possibles : `validé` · `supersédé par ADR-XXX` · `proposé` · `rejeté`.

---

## ADR-001 — Application modulaire à deux niveaux, monolithe

- **Date** : 2026-09-2X (session refactor V10)
- **Statut** : validé
- **Contexte** : le projet est passé d'un `app/agent/` monolithique à une structure à deux niveaux. 280 fichiers Python, 60 170 lignes, 200 fichiers TypeScript, 28 263 lignes.
- **Options** :
  1. Monolithe à plat `app/<domain>/` — simple, mais `app.agent` était le point de convergence de tous les couplages.
  2. **Monolithe modulaire à deux niveaux `app/{api,graph,services,repositories,infrastructure}/`** — retenu.
  3. Microservices — rejeté : deux services Docker au total, aucune équipe, aucun besoin d'échelle horizontale par domaine.
- **Décision** : monolithe modulaire. `api/` ne contient que des contrats HTTP, `services/` la logique métier, `repositories/` le SQL, `infrastructure/` les adaptateurs externes.
- **Conséquences** : 36 modules de compatibilité ont été supprimés à la fin du refactor (`71bbbb2`) et `grep "from app.agent"` retourne **0 résultat** — le nettoyage a fonctionné. Une vingtaine de fichiers portent encore `compatibilit|shim|legacy|deprecated` dans leur nom ou leur contenu : à traiter au fil de l'eau, jamais en une passe.
- **Revu si** : le projet dépasse 10 contributing developers, ou si un domaine doit être déployé indépendamment.

## ADR-002 — PostgreSQL (Neon) est la seule base de données

- **Date** : 2026-09-29
- **Statut** : validé
- **Contexte** : historiquement, `_build_engine()` (`infrastructure/database/connections.py:158`) construisait un engine SQLite si `DATABASE_URL` était absente. Sur Render, un secret manquant ne déclenche pas d'erreur de démarrage : le service démarrait, servait, et **écrivait dans un fichier local perdu à chaque redéploiement**. Le mode fail-open sur la donnée, alors que l'authentification était fail-closed.
- **Options** :
  1. Fail-open silencieux (état initial) — rejeté : perte de données invisible.
  2. **Fail-closed explicite** — retenu.
  3. Garde-fou SQLite en lecture seule — rejeté : deux chemins de code à maintenir, un seul est réel.
- **Décision** : `DATABASE_URL` est obligatoire. Son absence lève un `RuntimeError` au startup (`persistence.py:33-44`). `is_postgres_persistence()` retourne toujours `True` (`persistence.py:317`).
- **Conséquences** : il reste environ 200 lignes de code qui prétend encore supporter SQLite et qui est **inatteignable** — branche `else` de `_build_engine()`, `_sqlite_url()`, `get_checkpoint_engine()`, `CHECKPOINTS_DB_PATH`, et environ 150 lignes dans `services/documents/vector_store.py` (`import sqlite3`, `_SCHEMA_SQLITE`, `_is_postgres`, `_get_conn`, `_add_document_sqlite`). Le branche `"SQLite"` de `graph/main/graph.py:284` est mort. Nettoyage : `ROADMAP.md` lot B6.
- **Revu si** : un besoin de mode local hors-ligne apparaît (tests d'intégration sans base). Ce serait un **deuxième** chemin explicite, jamais un repli automatique.

## ADR-003 — Authentification par JWT Neon Auth, fail-closed

- **Date** : 2026-09-26 (migration depuis Clerk)
- **Statut** : validé
- **Contexte** : Clerk exigeait un domaine personnalisé, impossible sur `*.vercel.app`. Le projet est passé à Neon Auth.
- **Options** :
  1. Clerk — rejeté : contrainte de domaine bloquante, confirmée le 2026-09-26.
  2. **Neon Auth, vérification JWT par JWKS** — retenu.
  3. Session serveur — rejeté : aucun besoin de révoquer une session indépendamment du fournisseur d'identité.
- **Décision** : `AUTH_MODE=neon` en production. `PyJWKClient` en singleton paresseux (`resolver.py:65-84`) vérifie la signature ; le claim `sub` est résolu vers `user_id` interne via `users.clerk_user_id` (`resolver.py:129`).
- **Conséquences** : **provisionnement automatique au premier login** (`resolver.py:140-172`) — un utilisateur qui s'inscrit obtient sa ligne sans script de migration. Le rôle admin est dérivé de `clerk_user_id ∈ ADMIN_CLERK_IDS` (`resolver.py:144,159,172`).
- **Revu si** : le besoin de révocation unitaire d'une session apparaît (implique de revenir à une table de sessions).

## ADR-004 — Un `AUTH_MODE` inconnu renvoie 503, jamais un accès ouvert

- **Date** : 2026-09-26
- **Statut** : validé
- **Contexte** : un code de résolution d'identité qui retourne `None` en cas d'erreur produit un **fail-open** silencieux : toute requête passe avec un utilisateur `None`, ou pire, avec le premier rôle trouvé.
- **Options** :
  1. Retourner `None` et laisser les routes décider — rejeté.
  2. **Lever une erreur 503** — retenu.
- **Décision** : `resolver.py:269-282`. Les seuls modes acceptés sont `neon` et `dev`. Tout autre mode lève.
- **Conséquences** : un secret mal configuré casse l'API de manière **visible et immédiate**, ce qui est le comportement voulu en production. Le mode `dev` reste accessible si `AUTH_MODE=dev` est posé par erreur — c'est la seule faiblesse résiduelle, surveillée par l'endpoint `/api/health/auth`.
- **Revu si** : plus de deux modes existent, ou si un rôle « lecture seule public » est introduit.

## ADR-005 — Le schéma est appliqué au démarrage, sans version

- **Date** : héritage, non daté
- **Statut** : **proposé de remplacement** (voir ADR-005bis)
- **Contexte** : `infrastructure/database/schema.py` applique `CREATE TABLE IF NOT EXISTS` puis des `ALTER TABLE ADD COLUMN` inlines à chaque démarrage (`init_schema()`, l.311). Vérifié : il n'existe **aucun** dossier `migrations` et **aucun** `alembic.ini` dans le dépôt.
- **Options** :
  1. État initial — `CREATE IF NOT EXISTS` + `ALTER` inline.
  2. **Alembic** — proposé.
- **Décision** : aucune migration n'a jamais été écrite. Conséquence directe : une colonne mal typée est irrécupérable, et deux services qui démarrent avec des versions de code différentes peuvent laisser le schéma dans un état intermédiaire.
- **Conséquences** : les `ALTER` sensibles l.344, l.351 et l.363 (`object_storage.content DROP NOT NULL`) sont des modifications de données exécutées en production sans traçabilité.
- **Revu si** : la prochaine évolution du schéma est multi-version — c'est-à-dire maintenant.

### ADR-005bis — Alembic pour les migrations de schéma

- **Date** : 2026-09-29
- **Statut** : proposé
- **Contexte** : voir ADR-005. Le coût d'introduction est faible si on le fait **avant** la prochaine évolution de schéma : plus élevé après.
- **Options** :
  1. Introduire Alembic maintenant, avec un baseline du schéma existant — retenu.
  2. Continuer en `CREATE IF NOT EXISTS` — rejeté : la dette ne s'améliore pas toute seule.
- **Décision** : installer Alembic, générer un baseline reflétant le schéma actuel, puis faire passer toute évolution future par `alembic revision`. `init_schema()` reste en place **uniquement** pour la période de transition et perdra ce rôle à la migration complète.
- **Conséquences** : gain du rollback et de l'historique ; coût d'un cycle de migration à poser correctement. Rendu à : `ROADMAP.md` lot C1.
- **Revu si** : le projet passe en phase de maintenance sans évolution de schéma — dans ce cas l'introduction peut être repoussée, mais pas supprimée.

## ADR-006 — Cache in-process, et pourquoi cette décision est désormais fausse

- **Date** : 2026-09-2X (initial) / 2026-09-29 (réévaluation)
- **Statut** : **supersédé par ADR-006bis**
- **Contexte** : `infrastructure/cache/ttl.py:11-14` justifie explicitement l'absence de Redis par « plan Render free, un seul process, pas de Redis ».
- **Décision initiale** : cache mémoire du processus, invalidé par les fonctions d'écriture.
- **Problème** : **la prémisse « un seul process » est fausse.** `render.yaml` déploie `agent-tutor-api` et `agent-tutor-worker` depuis la même image. Le worker vocal lit la mémoire par les mêmes fonctions que l'API (`infrastructure/livekit/memory_tools.py:12-16`, `infrastructure/livekit/session.py:250-272`) mais **dans un autre processus**. Une invalidation faite par l'API ne purge pas le cache du worker.
- **Symptôme** : un utilisateur modifie son profil, démarre une session vocale, et l'agent tuteur lui parle avec l'ancien profil pendant 5 minutes. Aucun log, aucune erreur, invisible en local.

### ADR-006bis — Cache partagé entre l'API et le worker vocal

- **Date** : 2026-09-29 / **implémenté** 2026-09-30
- **Statut** : ~~validé · implémenté (lot D)~~ → **supersédé par ADR-026** (le worker vocal n'existe plus : il n'y a plus qu'un seul processus, donc plus rien à partager. Le contrat de cache, lui, reste entier)
- **Contexte** : le défaut décrit ci-dessus est structurel, pas un bug d'implémentation. Le corriger sans store partagé reviendrait à supprimer le cache.
- **Options** :
  1. Supprimer le cache — rejeté : le coût des lectures répétées sur la mémoire longue durée est réel, et le TTL reste une sécurité utile contre les invalidations oubliées.
  2. **Store partagé** — retenu.
  3. Court-circuiter le cache depuis le worker (lecture directe) — rejeté : contourne le problème sans rien gagner en complexité, et le worker perd la protection du TTL.
- **Décision** : introduire un store partagé accessible aux deux services. Fournisseur retenu : **Upstash** — offre gratuite 256 MB / 500 K commandes par mois / 10 000 commandes par seconde, sans carte bancaire, API REST compatible `@upstash/redis`. Le code ne doit dépendre que de l'API Redis, jamais du SDK d'un fournisseur.
- **Implémentation (2026-09-30)** :
  - `infrastructure/cache/base.py` : contrat `CacheBackend` (`get` / `set` / `invalidate` / `clear_prefix`) ; valeur `None` jamais stockée ; valeurs JSON-sérialisables ; un backend qui échoue retourne `None` et n'écrit rien — « le cache n'est pas une source de vérité ».
  - `infrastructure/cache/ttl.py` : `TTLCache` devient une implémentation mémoire du contrat (le bug `get_or` est supprimé, voir ADR-019).
  - `infrastructure/cache/redis_backend.py` : implémentation Redis via **redis-py** (client officiel ; mêmes URL `redis://` / `rediss://` pour compose, Upstash ou Layerbase). Import paresseux : sans le package, le backend ne peut pas exister — la fabrique retombe en mémoire, loggé.
  - `infrastructure/cache/factory.py` : `get_cache()` — `REDIS_URL` définie ET package présent → `RedisBackend`, sinon `TTLCache`. Repli silencieux MAIS loggé (une erreur par type toutes les 60 s côté Redis).
  - `services/memory/memory.py` : le cache de la mémoire longue durée passe par la fabrique (clés `mem:{user_id}:profile` / `mem:{user_id}:facts` inchangées).
  - `render.yaml` : `REDIS_URL` ( `sync: false` ) déclarée sur **l'API ET le worker** — c'est le cas d'usage exact : l'API invalide à l'écriture, le worker lit.
  - `docker-compose.yml` : service `redis` par défaut, `REDIS_URL` câblée sur `api` et `worker`.
  - `requirements.txt` : `redis>=5.0`.
- **Conséquences** : chaque appel LLM et chaque écrit en base génère une commande, donc un coût. L'offre gratuite est confortable à l'échelle actuelle mais devient fragile : **si le volume de commandes devient un coût, le palier suivant est Layerbase Solo (5 $/mois, prix fixe, commandes non facturées, API REST identique — la migration se réduit à changer l'URL)**. Upstash Fixed 250 MB à 10 $/mois est le repli classique si l'API REST devient une contrainte.
- **Ce qui ne sera jamais mis en cache** : les résultats LLM et les états de thread. Le checkpointer Postgres est la seule source de vérité (déclaration existante à conserver, `services/memory/memory.py:48-49`).
- **Revu si** : le plan Render devient payant et peut héberger un Redis en TCP natif — l'implémentation change, pas la décision. Ou si le volume de commandes dépasse durablement 500 K/mois sans budget.

## ADR-007 — Les résultats LLM et les états de thread ne sont jamais mis en cache

- **Date** : 2026-09-2X
- **Statut** : validé
- **Contexte** : la tentation est naturelle de mettre en cache les réponses du LLM pour économiser du tokens.
- **Options** :
  1. Cacher les réponses LLM — rejeté.
  2. **Ne pas les cacher** — retenu.
- **Décision** : un cache de réponses LLM produit un tuteur qui répète des réponses périmées, et casse l'apprentissage personnalisé. Les états de thread appartiennent au checkpointer Postgres.
- **Conséquences** : le cache reste limité aux **données de référence lues par une fonction et invalidées par les fonctions d'écriture** — la discipline est inscrite dans l'en-tête de `ttl.py:16-19`.
- **Revu si** : le modèle change et qu'un cache sémantique devient pertinent — mais ce serait alors un index vectoriel, pas un cache clé/valeur.

## ADR-008 — Deux services Render depuis une seule image Docker

- **Date** : 2026-09-2X
- **Statut** : ~~validé~~ → **supersédé par ADR-026** (le worker vocal est déployé sur LiveKit Cloud, il n'y a plus qu'un service Render)
- **Contexte** : le mode vocal exige un processus Python long-vivant avec un `AgentServer`. Le même code sert aussi d'API HTTP.
- **Options** :
  1. Un seul service qui fait les deux — rejeté : le worker consumes beaucoup de RAM (Silero VAD, ~200-300 Mo) et tuait l'API.
  2. **Deux services, une image, un drapeau `RUN_AS_WORKER`** — retenu.
  3. Deux images distinctes — rejeté : divergence de build garantie.
- **Décision** : `backend/render.yaml` déclare deux services qui construisent la **même image**. Le worker lance `python -m app.infrastructure.livekit.worker_main` avec `RUN_AS_WORKER=1`. Healthchecks distincts : `/api/health` pour l'API, `/healthz` pour le worker (200 seulement si le worker est enregistré auprès de LiveKit).
- **Conséquences** : les **credentials LiveKit doivent être partagés** entre les deux services — sinon le dispatch créé par l'API n'est jamais réclamé, et le piège est silencieux. Deux mémoires distinctes : voir ADR-006bis. `render.yaml` se déclare « source de vérité en plus du dashboard, le dashboard gagne ».
- **Revu si** : le projet passe au plan Render payant, ou si le worker vocal est remplacé par un service LiveKit Cloud entièrement managé.

## ADR-009 — Configuration des modèles déclarée en YAML, découplée des embeddings

- **Date** : Refactor V7.1
- **Statut** : validé
- **Contexte** : le modèle de génération change, le modèle d'embeddings change, et les deux n'ont aucune raison d'évoluer ensemble.
- **Options** :
  1. Constantes dans le code — rejeté : un changement de modèle impose un déploiement.
  2. **YAML déclaratif** — retenu.
- **Décision** : `app/models.yaml` pour la génération, `app/embeddings.yaml` pour les embeddings. `services/models/registry.py` lit et écrit le premier ; le second expose les providers avec leur dimension. La résolution d'affectation (utilisateur, groupe, capacité requise) est dans `services/models/resolver.py`.
- **Conséquences** : l'administration des modèles est une route API (`/api/admin/models`), donc pas de redéploiement. Le choix du modèle d'embeddings est **une ligne de YAML, zéro changement de code**. `EMBEDDING_PROVIDER` (env) surcharge le champ `active` pour les tests et l'exploitation.
- **Revu si** : le nombre de modèles dépasse quelques dizaines, ou si la sélection doit devenir dynamique par charge plutôt que par configuration.

## ADR-010 — Cinq sous-graphes LangGraph, choisis au runtime

- **Date** : Refactor V7/V10
- **Statut** : validé
- **Contexte** : coder, traiter un document, résoudre un exercice, faire une recherche web et indexer une vidéo sont cinq métiers distincts. Les mettre dans le graphe principal produisait un `workflow_router` de 300 lignes et un état géant.
- **Options** :
  1. Un seul graphe avec un routeur central — rejeté, déjà en place, complexité croissante.
  2. **Cinq sous-graphes, dispatch conditionnel** — retenu.
- **Décision** : `edges.py:125` porte le dispatch conditionnel vers `coding`, `document`, `problem`, `research`, `video`. Le nœud `agent` est lui-même un sous-graphe dynamique.
- **Conséquences** : chaque sous-graphe possède son propre `state.py` — les contrats sont isolés, mais un sous-graphe ne peut pas lire un canal écrit par un autre sans passer par `MainState`. Le graphe principal reste le seul point d'accès à la base.
- **Revu si** : un sixième sous-graphe apparaît qui partage plus de la moitié de son état avec un sous-graphe existant — signe qu'ils doivent fusionner.

## ADR-011 — VAD Silero chargé paresseusement, aucun processus préchargé

- **Date** : 2026-09-2X
- **Statut** : validé
- **Contexte** : le plan Render free offre 512 Mo de RAM par service. Le VAD Silero charge torch/onnxruntime, soit environ 200-300 Mo **par processus**.
- **Options** :
  1. VAD cloud (LiveKit Inference ou Deepgram) — rejeté : ajoute un coût par seconde de silence.
  2. **VAD local, `num_idle_processes=0`** — retenu.
- **Décision** : aucun agent préchargé ; l'agent en lance un à la demande, avec un cold start de quelques secondes. `vad=silero.VAD.load()` est appelé dans `build_session()`, donc seulement quand un job existe. **Depuis ADR-026 ce code vit dans `agent/session_factory.py` (projet autonome `agent/`), plus dans `backend/app/infrastructure/livekit/`.**
- **Conséquences** : le cold start de quelques secondes est accepté pour un tuteur vocal. Les logs LiveKit sont montés à `ERROR` (`agent.py:30-45`) parce que leur formatage synchrone bloquait la boucle audio jusqu'à 17 secondes sur le CPU partagé de Render — un défaut entendu en production.
- **Revu si** : le projet passe au plan Render payant (mémoire plus large) ou si le cold start devient perceptible par les utilisateurs.

## ADR-012 — Le VAD, le STT, le LLM et le TTS vocaux ne sont jamais inventés

- **Date** : 2026-09-2X
- **Statut** : validé
- **Contexte** : un nom de modèle inexistant dans le catalogue LiveKit Inference provoque un agent muet en salle — l'étudiant reste face au silence sans comprendre pourquoi.
- **Options** :
  1. Configurer le modèle par env sans validation — rejeté.
  2. **Valider contre le catalogue, avec repli** — retenu.
- **Décision** : `session.py:45` `_known_models()` interroge les enums `STTModels`, `LLMModels` et `TTSModels` du catalogue LiveKit Inference. `_validate_model()` (l.69) refuse un modèle absent et lève `PipelineBuildError`. L'API `/api/livekit` n'expose que des modèles déjà validés.
- **Conséquences** : `_LLM_FALLBACKS = ["openai/gpt-4o-mini", "google/gemini-2.5-flash"]` (l.40) garantit que l'agent a toujours un modèle de repli. `server.py:146-160` transforme l'erreur de configuration en un code d'erreur publié et actionnable au lieu d'un agent silencieux.
- **Revu si** : le catalogue LiveKit expose une API de validation stable permettant de supprimer le repli local.

## ADR-013 — Garde anti-boucle d'erreurs sur les sessions vocales

- **Date** : 2026-09-2X
- **Statut** : validé
- **Contexte** : une erreur RTC répétée peut faire boucler l'agent, saturer les logs et le CPU, et consommer le quota LiveKit.
- **Options** :
  1. Laisser les erreurs remonter — rejeté.
  2. **Compteur de seuil, arrêt ordonné** — retenu.
- **Décision** : `infrastructure/livekit/errors.py` (372 lignes) : `classify_exception` attribue un code, `ErrorGuard` compte, `attach_error_handler` s'attache **avant** `session.start()` (les événements « error » peuvent être émis dès les premières millisecondes), et `_on_fatal` (`server.py:175-191`) annonce vocalement l'erreur puis ferme la session.
- **Conséquences** : l'étudiant entend une explication plutôt que le silence. Chaque erreur de RTC est **publiée** (`publish_error`) donc consultable depuis l'API d'administration.
- **Revu si** : LiveKit fournit un mécanisme natif de limitation de tentatives.

## ADR-014 — RAG sur pgvector, repli lexical en cas de panne

- **Date** : Refactor V7.1
- **Statut** : validé
- **Contexte** : le modèle d'embeddings peut être absent, le service indisponible, ou la dimension incompatible avec la colonne existante.
- **Options** :
  1. Échec fermé — rejeté : l'agent tuteur devient muet si le RAG tombe.
  2. **Repli fail-safe sur la recherche lexicale** — retenu.
- **Décision** : `services/documents/vector_store.py` — index HNSW `vector_cosine_ops`, seuil cosine `0.6`, toute erreur de store remonte `RagStoreError` et le routing bascule sur la recherche lexicale. Dimension lue depuis `embeddings.yaml`. Plafond pgvector à 16 000 dimensions (`_PGVECTOR_MAX_DIM`, l.82).
- **Conséquences** : une dégradation de qualité est possible en cas de panne sans interruption de service. C'est un compromis assumé pour un produit pédagogique.
- **Revu si** : la qualité de retrieval devient l'objet d'une évaluation de qualité mesurée — le repli Stop alors d'être acceptable.

## ADR-015 — CORS : une seule source de vérité, le backend

- **Date** : 2026-09-29
- **Statut** : **appliqué** (B1) · **corRigé le 2026-09-29 après vérification du chemin réel**
- **Contexte** : `app/main.py:109` installe un `CORSMiddleware` paramétré par `ALLOWED_ORIGINS`, et `backend/render.yaml` documente cette variable comme **obligatoire en production**. Mais `vercel.json` déclarait sur `/api/(.*)` un en-tête `Access-Control-Allow-Origin: *` qui semblait court-circuiter cette protection.
- **Options** :
  1. Laisser le `*` — rejeté : incohérent avec la décision d'authentification fail-closed d'ADR-004.
  2. **Supprimer les en-têtes CORS de `vercel.json` et laisser le backend répondre** — retenu.
- **Décision** : `vercel.json` ne déclare plus d'en-têtes CORS. Une seule politique s'applique, celle du backend.
- **⚠️ Ce que la vérification du 2026-09-29 a corrigé** : le raisonnement initial était juste dans sa conclusion, faux dans son mécanisme. `frontend/.env.production:14` fixe `VITE_API_URL=https://agent-tutor-api.onrender.com`, et `src/api/base.ts:14` en fait `BASE` → **le navigateur appelle Render directement, en cross-origin**. Le trafic de production ne passe donc **pas** par le proxy Vercel, et les en-têtes supprimés s'appliquaient à une origine qui n'était jamais sollicitée pour l'API. Ils étaient donc **inertes**, pas dangereux sur le chemin réel. Le retrait ne change aucun comportement — et il ne répare rien non plus.
- **Le vrai problème n'était pas là** : j'ai d'abord conclu que `ALLOWED_ORIGINS=http://localhost:5173` sur Render bloquait toute la production. **C'était faux** : je lisais le fichier, pas l'état déployé — alors que `render.yaml:3-7` dit lui-même que le dashboard prime. Vérification faite le 2026-09-29 par `curl -H "Origin: …"` contre l'API en production, le domaine Vercel est accepté, `localhost:5173` est accepté, et une origine tierce ne reçoit **aucun** en-tête ACAO. **La production fonctionne et le CORS est correctement fail-closed.** Le défaut était documentaire : `render.yaml` décrivait une valeur qui aurait cassé la prod si un `blueprint apply` l'avait appliquée. Corrigé.
- **Ce qui reste vrai** : le dépôt contient deux stratégies de transport concurrentes (proxy Vercel vs appel direct), non tranchées, et une seule route (`src/api/events.ts:12`, `new EventSource('/api/events')` en URL relative) suit la première — sans jeton, donc en 401 permanent, puisque `app/logging/sse.py:19-43` exige un en-tête `Authorization` ou un paramètre `?auth=`.
- **Effet de bord à assumer** : Starlette n'accepte pas de jokers, donc les domaines de prévisualisation Vercel (`frontend-<hash>.vercel.app`) sont refusés. Tester une branche en preview exige d'ajouter son domaine à la liste.
- **Conséquences** : le mode **B — appel direct à Render** est celui qui tourne en production (vérifié dans le bundle déployé : `https://agent-tutor-api.onrender.com` y figure). C'est aussi le bon choix — le proxy Vercel n'apporte rien devant un Render free qui suspend déjà, et il ajoute un saut. La réécriture `/api/:path*` de `vercel.json` n'est donc plus utilisée que par `events.ts`.
- **Revu si** : un client non-navigateur consomme l'API (webhooks LiveKit, MCP distants) — il faudra un allowlist explicite, décidé à ce moment-là.
- **Rendu à** : `ROADMAP.md` B1 (fait), B1bis (tranché par la vérification : mode B), B2 (vérifié correct, fichier aligné).

## ADR-016 — La CI ne bloque pas sur les tests ni sur le lint

- **Date** : après une série de pannes de livraison
- **Statut** : **proposé de correction**
- **Contexte** : l'en-tête de `.github/workflows/ci.yml` rappelle que « trois poussées consécutives ont cassé la production (Render) à cause d'imports morts et d'un package PyPI inexistant ». La réponse donnée à ces échecs d'infrastructure a été d'affaiblir la CI.
- **Options** :
  1. `continue-on-error` sur tests et lint — état actuel.
  2. **CI bloquante stricte** — rejeté immédiatement : elle re-bloquerait les livraisons pour des raisons d'infrastructure.
  3. **CI bloquante par étapes, avec un budget d'échecs explicite** — retenu.
- **Décision** : rétablir le blocage **progressivement**, jalon par jalon, en distinguishing les échecs de **code** des échecs d'**infrastructure**. Le premier jalon : `compileall` et les smoke imports doivent bloquer (ils l'font déjà) ; ajouter progressivement `pytest` sur les suites non-régressives, puis le lint.
- **Conséquences** : le risque est de ne jamais franchir la première étape. Un `ROADMAP.md` lot B5 rend l'étape explicite et datée.
- **Revu si** : le projet part en maintenance sans nouvelle fonctionnalité — dans ce cas la CI puede rester souple.

## ADR-017 — `clerk_user_id` : un nom historique pour une colonne d'identité externe

- **Date** : 2026-09-26
- **Statut** : **en attente de décision — risque réel**
- **Contexte** : Clerk a été écarté, mais la colonne `users.clerk_user_id` est restée. Ce n'est plus un artefact Clerk : c'est **la colonne d'identité externe**, dans laquelle Neon Auth écrit (`auth/resolver.py:284`).
- **Options** :
  1. Renommer en `external_user_id` — plus juste, mais migration sur la base Neon live avec un index unique partiel `idx_users_clerk` (`infrastructure/database/connections.py:103-117`).
  2. **Conserver le nom actuel** — état actuel.
- **Décision** : **non tranchée.** Le choix appartient au projet, pas à une décision technique par défaut.
- **Conséquences de l'option 1** : le nom devient exact, ce qui réduit la confusion pour les nouveaux contributeurs. Coût : une migration sur une base live.
- **Conséquences de l'option 2** : aucun coût, mais le nom induit en erreur et le code le signale depuis trois mois.
- **Revu si** : **la décision doit être prise avant la prochaine migration de schéma** — c'est le moment naturel, et il est imminent (ADR-005bis).

## ADR-018 — `ADMIN_CLERK_IDS` → `ADMIN_EXTERNAL_IDS` : renommage fait, repli à retirer

- **Date** : 2026-09-26 (signalé) / 2026-09-29 (vérifié : déjà fait)
- **Statut** : validé — il ne reste qu'une décision de retrait
- **Contexte** : le rôle admin est déterminé par appartenance de l'identifiant externe à une liste. Le nom `ADMIN_CLERK_IDS` était obsolète depuis le passage à Neon Auth.
- **Options** :
  1. Conserver le nom obsolète — rejeté : le nom induit en erreur.
  2. **Renommer avec repli, puis retirer le repli** — retenu.
  3. Renommer sans repli — **rejeté, et c'est le piège à éviter** : une variable d'environnement absente ne produit aucune erreur. L'application démarre normalement avec **zéro administrateur**. C'est une perte de privilège silencieuse, pas une panne.
- **Décision** : `app/config.py:119-123` lit `ADMIN_EXTERNAL_IDS` et, à défaut, `ADMIN_CLERK_IDS`. Le commentaire l.104-117 documente la période de transition. Le code métier n'utilise plus que `ADMIN_EXTERNAL_IDS` (`auth/resolver.py:145,161,177,231` et `api/users.py:34,98`).
- **Conséquences** : la transition sûre est **déjà en place** — c'est la partie difficile. Restent deux actions, toutes deux à faire avec la même prudence :
  1. Vérifier que `ADMIN_EXTERNAL_IDS` est posée sur **tous** les environnements (local, Render, preview). Tant qu'un seul lit l'ancien nom, le repli est nécessaire.
  2. Une fois cette vérification faite et tracée, retirer `os.getenv("ADMIN_CLERK_IDS", "")` de `config.py:122-123`.
- **Piège à connaître** : `ADMIN_EXTERNAL_IDS` compare des **noms** en mode `dev` (`api/users.py:98` : `"dev-admin"`) et des **identifiants externes** en mode `neon` (`resolver.py:145`). Une même variable, deux types de valeur selon le mode. C'est source de confusion et mérite un commentaire.
- **Revu si** : `ADMIN_EXTERNAL_IDS` est confirmée sur tous les environnements — le repli peut alors être retiré, et cette entrée est close.

## ADR-019 — Le contrat de cache : `CacheBackend`, implémenté par mémoire et Redis

- **Date** : 2026-09-2X / **réserves levées** 2026-09-30
- **Statut** : validé
- **Contexte** : le cache a été conçu pour être remplaçable par Redis sans changer les appelants.
- **Décision** : le contrat est désormais formel : `infrastructure/cache/base.py` définit `CacheBackend` ( `get` / `set` / `invalidate` / `clear_prefix` ), implémenté par `TTLCache` ( mémoire, in-process ) et `RedisBackend` ( redis-py, partagé — ADR-006bis ). La sélection se fait dans `factory.get_cache()` ; les services ( ex. `services/memory/memory.py` ) ne manipulent jamais une classe concrète. Règles du contrat : **`None` n'est jamais stocké**, les valeurs sont **JSON-sérialisables**, un backend qui échoue retourne `None` et n'écrit rien.
- **Réserves de l'audit initial, résolues ou assumées** :
  1. `get_or()` était un **bug** ( `ttl.py:71-73` : deux appels à `get()`, double verrou, fenêtre d'expiration ) — **supprimé** : il n'avait aucun appelant.
  2. `clear_prefix()` est **conservé** : `RedisBackend` l'implémente par `SCAN` + `DEL` ( coût réel mais borné par les TTL ; retourne le nombre de clés supprimées ), `TTLCache` par parcours du dict. L'interface retourne `int` ( compte supprimé ; `-1` côté Redis si injoignable ).
  3. L'éviction de `TTLCache` est **FIFO** ( pas LRU ) — documenté et assumé.
  4. **Métriques hit/miss** : toujours à faire ( hors lot D ) — savoir si le cache sert avant d'en payer le coût. `log_event("MEMORY_READ", extra={"cached": True})` existe dans `services/memory/memory.py` mais n'est agrégé nulle part.
- **Revu si** : un besoin d'invalidation par motif apparaît à grande échelle ( des dizaines de clés par préfixe, à chaque appel ) — dans ce cas, `clear_prefix` côté Redis doit être repensé ( index dédié, `unlink`, ou renoncement au motif ).

## ADR-020 — Une seule image, un seul registre d'outils, un seul point d'entrée d'authentification

- **Date** : Refactor V10
- **Statut** : validé
- **Contexte** : un projet de cette taille accumule vite les chemins parallèles qui divergent silencieusement.
- **Décision** : trois invariants vérifiables mécaniquement.
  1. **Authn** : `auth/resolver.py` est le seul point d'entrée. Aucun module ne lit un token par lui-même.
  2. **Outils LLM** : `app/tools/__init__.py` expose `all_tools`. La CI échoue si le registre ne s'importe pas — garde réelle, pas une intention.
  3. **Config** : `config.py` est le seul lecteur d'environnement. Aucun `os.environ` dispersé.
- **Conséquences** : ces invariants sont la seule chose qui distingue cette architecture d'un empilement. Ils doivent rester vérifiables par une commande unique.
- **Revu si** : un besoin légitime d'authentification par service tiers apparaît (webhooks LiveKit, MCP distants) — dans ce cas, l'exception doit être explicite et nommée, pas un `if` ajouté au premier besoin.
## ADR-021 — Topologie de développement local : `docker-compose.yml`

- **Date** : 2026-09-29
- **Statut** : **proposé, non testé** (Docker absent de la machine de développement)
- **Contexte** : le repli SQLite a été retiré (ADR-002, même jour). Conséquence non anticipée : le développeur local n'avait plus **aucune** base de données. Les seules options étaient de pointer sur Neon depuis la machine — donc d'écrire sur les données de production au premier test Approbation — ou de ne plus développer. Le dépôt n'avait aucun `compose.yaml`.
- **Options** :
  1. **Ne rien faire** — rejeté : la décision ADR-002 a retiré un filet de sécurité sans le remplacer. Elle a créé un risque (données de production en local) plus grave que celui qu'elle supprimait.
  2. **Un Postgres local seul, backend hors conteneur** — écarté : simple, mais ne reproduit pas la contrainte qui compte, à savoir les **2 processus** de `render.yaml` (API + worker vocal). C'est précisément elle qui a produit le défaut de cache documenté en ADR-006bis.
  3. **`docker-compose.yml` reproduisant la topologie de prod** — retenu.
- **Décision** : `docker-compose.yml` à la racine, 4 services — `db` (`pgvector/pgvector:pg16`) et `api` par défaut ; `redis` et `front` sous profils. Le service `worker` et le profil `voice` ont été supprimés avec ADR-026 : l'agent vocal n'a rien à lancer en local, il tourne sur LiveKit Cloud.
- **Choix non évidents, et leur raison** :
  - Le worker est **supprimé** (il était sous profil, pas par défaut : il s'inscrivait auprès de LiveKit Cloud et pouvait, avec de vraies credentials, réclamer de vrais dispatchs).
  - `redis` est **déclaré mais sous profil** : le contrat de cache n'existe pas encore (ADR-019). Déclarer un service que le code ignore donne l'illusion d'une architecture distribuée — c'est précisément le crime que ce projet s'efforce d'éviter ailleurs.
  - `DATABASE_URL` est surchargée dans `environment:` et pas seulement dans `env_file` : sans surcharge, le conteneur hériterait de l'URL Neon du `.env` local.
  - Deux correctifs `vite.config.ts` ont été nécessaires au service `front` : `strictPort: true` (sinon Vite décale sur 5174 et le CORS du backend, qui n'autorise que 5173, rejette tout en silence) et `VITE_DEV_API_TARGET` (le proxy était codé en dur sur `localhost:8000`, qui désigne le conteneur Vite lui-même).
- **Conséquences** : le dev local se fait sur le même SGBD, avec la même extension vectorielle. En contrepartie, **ce qui ne se teste qu'en production** reste non testé en local : le pooler Neon, l'autoscaling CU, le scale-to-zero, et l'absence de limite mémoire (512 Mo sur Render, aucune ici — une fuite mémoire ne se voit pas en local).
- **⚠️ Statut de vérification** : le YAML est syntaxiquement valide et la topologie a été relue, mais **aucun `docker compose up` n'a été exécuté** — Docker n'est pas installé sur la machine (`docker: command not found`). Ne pas traiter ce fichier comme validé en fonctionnement.
- **Revu si** : le CI passe en conteneurs (le compose devient la base du job d'intégration — à ce moment il doit être testé, pas relu) ; ou si le disque machine ne permet pas de construire l'image (torch + ffmpeg pèsent plusieurs Go, cf. l'alerte disque de 100 %).

---

## ADR-022 — Architecture multiservice : le service d'authentification est extrait, la vérification reste locale

- **Date** : 2026-09-30
- **Statut** : validé (décision produit de l'équipe : migration vers une architecture multiservice)
- **Contexte** : le projet passe d'un monolithe modulaire à deux niveaux (ADR-001) à une **architecture multiservice**. Le premier service extrait est l'authentification, qui n'est pas un simple composant : c'est le chemin de 100 % du trafic. La question structurante n'est pas « quel framework » mais « où passe la frontière entre ce qui est centralisé et ce qui doit rester local ».
- **Options** :
  1. **Service d'auth HTTP qui vérifie les JWT à distance (appel réseau par requête)** — rejeté : la vérification est une crypto locale pure (clé publique JWKS). La centraliser par réseau ajoute une latence sur 100 % du trafic, une dépendance dure (le métier tombe si l'auth tombe), et un nouveau mode de panne pour zéro gain de sécurité — la confiance vient de la signature, pas de l'endroit où on la vérifie.
  2. **Vérification en bibliothèque partagée `auth-core`, émission/session/projection/rôle centralisés dans le service d'auth (Auth N + Auth Z)** — retenu. Chaque service vérifie le JWT localement via `auth-core` ; le service d'auth reste l'unique autorité pour créer les comptes, gérer les sessions, projeter `public.users` et attribuer le rôle.
  3. **Tout laisser dans le monolithe** — écarté : contredit la décision produit.
- **Décision** :
  1. `auth/resolver.py` ne devient **pas** un service HTTP : il devient la bibliothèque `auth-core` (vérification JWKS, `CurrentUser`, `get_current_user`, `require_admin`, `optional_current_user`), importée par chaque service. Une règle d'autorisation ne peut pas diverger d'un service à l'autre : il n'en existe qu'une copie.
  2. Le **service d'authentification** (déployable autonome) détient : délé ation au fournisseur d'identité (Neon Auth managé), vie de session, projection `public.users`, attribuer le rôle, endpoints `/sign-in`, `/sign-up`, `/verify-email`, `/users/me`.
  3. Le fournisseur d'identité reste **Neon Auth managé** (Better Auth 1.6.23) : le service d'auth ne réimplémente pas la vérification de mot de passe ni l'émission de JWT — il orchestre et projette.
  4. **Supersède ADR-001** pour ce qui concerne la topologie de déploiement (la structure modulaire du code reste, elle est simplement déployée en plusieurs services).
  5. **Corrige ADR-015** : l'affirmation « tout le trafic passe par le proxy Vercel » est fausse — deux chemins coexistent aujourd'hui (`apiFetch` en absolu cross-origin via `VITE_API_URL`, et 4 fetch bruts en relatif via le rewrite `vercel.json:27-31`). En multiservice, une seule forme d'URL doit survivre (voir EX-4 d'`AUTH_REQUIREMENTS.md`).
- **Conséquences** :
  - Le service d'auth et les services métier partagent `public.users` (même Postgres) : la frontière de service est logique, pas physique, au moins dans un premier temps. La séparation physique (base dédiée par service) est un chantier ultérieur, non décidé ici.
  - `ADMIN_EXTERNAL_IDS` (variable d'env) + `users.role` (miroir) : c'est **la** première question à trancher quand le service devient autonome — l'écart EF-14 d'`AUTH_REQUIREMENTS.md` est la seule raison d'exister du service en propre.
  - Aucun secret d'auth ne doit transiter vers le frontend ; le service d'auth reste le seul à parler au fournisseur d'identité.
  - Le référentiel d'exigences détaillé (EF/ES/EO/EX, écarts numérotés) est dans `AUTH_REQUIREMENTS.md`.
- **Revu si** : un second service est extrait — auquel cas la frontière « bibliothèque partagée vs appel réseau » doit être re-tranchée pour ce service précis, et la décision de séparation physique des bases doit être prise explicitement.

---

## ADR-023 — Rôle administrateur : `users.role` est l'unique autorité au runtime, la variable d'environnement n'est qu'un bootstrap

- **Date** : 2026-09-30
- **Statut** : validé
- **Contexte** : c'est l'écart EF-14 d'`AUTH_REQUIREMENTS.md`, désigné par ADR-022 comme la première décision à rendre. Deux mécanismes se superposent : `ADMIN_EXTERNAL_IDS` (variable d'env, liste de `sub` externes) **prime** sur `users.role` — le résolveur force `role="admin"` quel que soit le contenu de la base, et **persiste l'écart** via `set_user_role` (`resolver.py:149-156`) pour que l'UI affiche le même rôle que l'autorisation. Conséquence : la variable prime et la base est un miroir — un retrait de variable ne rétrograde personne.
- **Options** :
  1. **Variable d'env seule** — rejetée : en multiservice, la liste devrait être dupliquée dans **chaque** service qui importe `auth-core`, or `auth-core` est une bibliothèque, pas un service — elle ne peut pas centraliser une configuration serveur. Rétrogradation impossible sans déploiement, aucune gestion par l'UI, changement invisible et non auditable. Une variable vide et un identifiant faux ont le même effet : zéro admin, sans avertissement.
  2. **`users.role` seule (base), avec bootstrap par variable d'env** — retenue : un seul endroit où le rôle vit, lu par chaque service via la projection `public.users`. Rétrogradation immédiate (`UPDATE`), ouvrable à une future page d'administration, auditable.
  3. **`users.role` seule, sans bootstrap** — écartée : personne ne peut promouvoir le premier admin sans UI ni outil.
- **Décision** :
  1. `users.role` est **l'unique autorité au runtime**. `ADMIN_EXTERNAL_IDS` ne sert qu'au **bootstrapping initial** : promouvoir les premiers administrateurs au moment du premier déploiement, puis elle est retirée des services.
  2. **Suppression de la persistance d'écart automatique** (`set_user_role` appelé depuis le résolveur) : un écart entre variable et base doit devenir **visible** (journalisé), jamais auto-réparé — sinon c'est une écriture magique qui réplique la config dans les données.
  3. Le repli legacy `ADMIN_CLERK_IDS` est retiré une fois `ADMIN_EXTERNAL_IDS` posée sur **tous** les environnements (Render compris) — il ne disparaît pas avant.
- **Conséquences** : le rôle lu par `GET /api/users/me` devient le rôle effectivement appliqué (ferme les écarts EF-15/EF-16 : plus de downgrade silencieux possible par lecture divergente). La promotion d'un développeur passe par un `UPDATE` SQL (ou une future page admin), pas par un redémarrage. Le résolveur final garde `require_admin` fail-closed : rôle absent → utilisateur ordinaire.
- **Revu si** : le fournisseur d'identité expose des claims de groupe (OIDC) — la base redeviendrait une projection du fournisseur, comme `external_user_id`.

---

## ADR-024 — Transport du jeton : jamais en query string (ES-5)

- **Date** : 2026-09-30
- **Statut** : validé
- **Contexte** : l'écart ES-5 d'`AUTH_REQUIREMENTS.md` — `logging/sse.py:36` et `ws/logs.py:24` lisaient le jeton dans `query_params`. Le jeton atterrissait donc dans les journaux d'accès Render, les journaux de proxy et l'historique du navigateur. Le fallback `?auth=` existait parce que l'`EventSource` natif ne porte pas d'en-tête ; mais le frontend réel était déjà passé en `fetch` + `ReadableStream` avec header Bearer (lot 1, EF-18) — le fallback ne servait plus à aucun client vivant. Le WebSocket `/ws/logs` n'avait aucun client (0 `new WebSocket` actif côté frontend) et aucun test.
- **Options** :
  1. **Garder `?auth=` en fallback** — rejetée : le jeton continue d'être exposé dans les journaux et l'historique, pour un client qui n'existe plus.
  2. **Supprimer tout transport par query string, retirer l'endpoint mort** — retenue : SSE = header Bearer uniquement (le seul client réel le fait déjà) ; `/ws/logs` et `wsUrl` supprimés.
  3. **Réécrire `/ws/logs` en header** — écartée : sans client, réécrire un endpoint mort est de la sur-ingénierie ; on le supprime, on le reconstruira avec un vrai client si le besoin revient.
- **Décision** : le jeton ne transite que par `Authorization: Bearer`. `sse.py` rejette 401 sans header ; le fallback `?auth=`, le dossier `app/ws/`, l'import et le montage dans `main.py`, et `wsUrl` de `base.ts` sont supprimés.
- **Conséquences** : plus aucune exposition du jeton par les journaux d'accès ni l'historique navigateur ; `GET /api/events` exige un header (compatible avec le client réel). Toute future connexion navigateur temps réel (SSE ou WebSocket) devra passer par `fetch` (SSE) ou un client qui sait poser l'en-tête — jamais l'URL.
- **Revu si** : un vrai besoin client impose `EventSource` natif ou un WebSocket navigateur — auquel cas il faudra un jeton à durée de vie très courte à usage unique échangé par un endpoint authentifié, pas une requête directe avec jeton en URL.
---

## ADR-025 — Changement de rôle : route admin explicite `PUT /api/admin/users/{user_id}/role`

- **Date** : 2026-09-30
- **Statut** : validé
- **Contexte** : l'ADR-023 a retiré l'auto-persistance d'écart du résolveur et posé `users.role` comme autorité unique au runtime, avec comme conséquence assumée « la promotion d'un développeur passe par un `UPDATE` SQL (ou une future page admin) ». Il manquait le canal d'écriture explicite côté API : sans lui, la seule voie est un accès SQL direct, non auditable côté applicatif, et aucune page d'admin frontend future ne peut s'appuyer sur un contrat stable.
- **Options** :
  1. **`PATCH /api/users/{user_id}/role` propriétaire** — rejetée : l'ownership autorise un user à modifier ses propres données ; un user pourrait se promouvoir admin sur sa propre ligne. Le rôle est une donnée d'autorisation : seuls les admins peuvent l'écrire.
  2. **`PUT /api/admin/users/{user_id}/role` admin uniquement** — retenue : route sous le préfixe admin existant, protégée par le même `require_admin` que toutes les routes d'administration ; body `{role: "admin"|"user"}` clos par un `Literal` (422 sur toute autre valeur) ; anti-lockout : un admin ne peut pas modifier son propre rôle.
  3. **Page SQL managée côté frontend** — écartée : la page admin n'existe pas encore ; l'ADR-023 dit « future page admin », la route API est le prérequis que cette page consommera.
- **Décision** : nouvelle route `PUT /api/admin/users/{user_id}/role` dans `backend/app/api/admin/users.py`, montée sans préfixe supplémentaire (préfixe interne `/api/admin/users`), `Depends(require_admin)`, 404 si cible inconnue, 422 si auto-modification, log `USER_ROLE_SET` existant réutilisé via `users_db.set_user_role`.
- **Conséquences** : la promotion/rétrogradation devient auditable (log événement), testable (Postman UR1), et consommable par une future page admin sans réouvrir le resolver. L'ADR-023 reste inchangé côté runtime : le rôle lu en base est le rôle appliqué.
- **Revu si** : un mécanisme multi-rôles plus riche (ROLE, RBAC par ressource) remplace un jour le couple `admin`/`user`.

## ADR-026 — L'agent vocal vit sur LiveKit Cloud, plus de worker dans l'image backend

- **Date** : 2026-10-01
- **Statut** : validé · implémenté
- **Contexte** : le worker vocal (`agent-tutor-worker`) était un service Render `free` de 512 Mo qui hébergeait un `AgentServer` LiveKit, avec une cold start de quelques secondes à chaque job, un VAD Silero chargé en mémoire (~200-300 Mo) et un piège de conception fragile : **les credentials LiveKit devaient être identiques entre l'API et le worker**, faute de quoi le dispatch créé par l'API n'était jamais réclamé — en silence, sans log d'erreur. Deux services, deux quotas de plan gratuit, une RAM divisée par deux, et un pipeline de déploiement local (Docker) devenu inutilisable pour tester quoi que ce soit.
- **Options** :
  1. **Rien changer** — rejeté : le piège des credentials partagés et la RAM divisée sont structurels, pas des bugs.
  2. Passer le worker au plan payant — écarté : ne corrige aucun des deux défauts, et ça coûte de l'argent.
  3. **Agent managé LiveKit Cloud, dossier `agent/` autonome** — retenu.
- **Décision** : l'agent est déployé sur **LiveKit Cloud** (agent `tutor`, projet `live`, région `eu-central`) via `lk agent deploy`, depuis le dossier **`agent/`** qui est un **projet Python autonome** (`agent.py`, `config.py`, `session_factory.py`, et à terme `memory_tools.py`). Raison structurelle : le contexte de build distant LiveKit ne peut être **qu'un seul dossier**, donc toute référence `../backend/app` échoue — d'où l'interdiction de dupliquer `backend/app/` dans `agent/`. Conséquences en chaîne :
  - `backend/app/infrastructure/livekit/` est réduit à `browser.py` + `constants.py` + `token.py` (capture d'écran et jetons). Les 9 fichiers du worker (`worker_main.py`, `server.py`, `session.py`, `agent.py`, `errors.py`, `memory_tools.py`, `config.py`, `transcript.py`, `gradium-marius.wav`) sont supprimés.
  - `render.yaml` ne déclare **qu'un** service ; le drapeau `RUN_AS_WORKER` disparaît, ainsi que le healthcheck `/healthz` et la duplication des credentials.
  - `Dockerfile` a un **rôle unique** : `CMD exec python -m uvicorn app.main:app`.
  - **Les outils mémoire passent en HTTP** : l'agent appelle `GET`/`POST /api/agent-memory/{user_id}/...` sur l'API, authentifié par un en-tête `X-Service-Secret`. `services/memory/memory.py` (985 lignes) n'est **pas** porté dans `agent/` — une seule implémentation de la mémoire, dans le backend.
  - **La source de vérité du prompt** devient `agent/config.py::BASE_INSTRUCTIONS` ; le prompt du backend a été retiré.
- **Conséquences** :
  - **ADR-006bis devient caduc dans son motif** (plus de deux processus → plus de cache à partager), mais **son contrat reste valide** : `CacheBackend` / `TTLCache` / `RedisBackend` continuent de fonctionner, `REDIS_URL` reste déclarée sur l'API.
  - **ADR-008 est supersédé** : un seul service Render, une seule image, un seul rôle.
  - La RAM de l'API n'est plus divisée ; le worker ne consomme plus de quota de plan gratuit.
  - Le piège du partage de credentials disparaît **par construction** : il n'y a plus qu'un seul jeu de credentials côté serveur, celui de l'API, et l'agent porte le sien.
  - Coût : le démarrage à froid dépend de LiveKit et non plus de Render, et le service managé entre dans la facture à l'usage.
  - Conséquence de test : **plus aucun build local possible** (Docker ne démarre pas sur la machine de dev) — `python -m compileall -q app ../agent` est la seule vérification statique disponible en local, d'où son ajout au job « Syntax check » de la CI.
- **Revu si** : LiveKit Cloud devient plus cher que l'hébergement du worker (politique de prix inchangée), ou si le projet doit rester 100 % auto-hébergé sans dépendance à un service managé.
