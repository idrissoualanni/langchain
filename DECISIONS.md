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

- **Date** : 2026-09-29
- **Statut** : proposé
- **Contexte** : le défaut décrit ci-dessus est structurel, pas un bug d'implémentation. Le corriger sans store partagé reviendrait à supprimer le cache.
- **Options** :
  1. Supprimer le cache — rejeté : le coût des lectures répétées sur la mémoire longue durée est réel, et le TTL reste une sécurité utile contre les invalidations oubliées.
  2. **Store partagé** — retenu.
  3. Court-circuiter le cache depuis le worker (lecture directe) — rejeté : contourne le problème, Complexité gagnée nulle, et le worker perd la protection du TTL.
- **Décision** : introduire un store partagé accessible aux deux services. Fournisseur retenu : **Upstash** — offre gratuite 256 MB / 500 K commandes par mois / 10 000 commandes par seconde, sans carte bancaire, API REST compatible `@upstash/redis`. Le code ne doit dépendre que de l'API Redis, jamais du SDK d'un fournisseur.
- **Conséquences** : chaque appel LLM et chaque écrit en base generates une commande, donc un coût. L'offre gratuite est confortable à l'échelle actuelle mais devient fragile enibb : **si le volume de commandes devient un coût, le palier suivant est Layerbase Solo (5 $/mois, prix fixe, commandes non facturées, API REST identique — la migration se réduit à changer l'URL)**. Upstash Fixed 250 MB à 10 $/mois est le repli classique si l'API REST devient une contrainte.
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
- **Statut** : validé
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
- **Décision** : `AgentServer(num_idle_processes=0)` (`infrastructure/livekit/server.py:62`). Aucun agent préchargé ; le worker en lance un à la demande, avec un cold start de quelques secondes. `vad=silero.VAD.load()` est appelé dans `build_session()` (`session.py:168`), donc seulement quand un job existe.
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

## ADR-019 — L'interface `TTLCache` est le contrat d'un cache futur

- **Date** : 2026-09-2X
- **Statut** : validé, avec réserves
- **Contexte** : le cache a été conçu pour être remplaçable par Redis sans changer les appelants.
- **Décision** : l'interface `get` / `set` / `invalidate` est conservée telle quelle par ADR-006bis.
- **Réserves** : deux défauts de l'interface doivent être corrigés avant toute substitution.
  1. `get_or()` (`ttl.py:71-73`) est un **bug** : `return self.get(key) if self.get(key) is not None else default` appelle `get()` **deux fois** — double verrou, et une fenêtre d'expiration entre le test et le retour. Cela ne distingue pas « absent » d'un `None` légitime, ce que la docstring de `get()` (l.56) signale pourtant. Il n'a **aucun appelant** : à supprimer.
  2. `clear_prefix()` (l.91-103) n'a **aucun appelant** et **n'a pas d'équivalent Redis** (`SCAN` + `DEL` est nettement plus coûteux qu'un `DEL` sur un motif). Une implémentation Redis ne doit pas promettre ce contrat.
  3. L'éviction est **FIFO** (l.80-84), pas LRU. Documenté et assumé, mais à savoir.
  4. Aucune **métrique hit/miss**. `log_event("MEMORY_READ", extra={"cached": True})` existe dans `services/memory/memory.py:446-458` mais n'est agrégé nulle part — il faut savoir si le cache sert avant d'en payer.
- **Revu si** : un besoin d'invalidation par motif apparaît réellement — auquel cas il faut concevoir ce contrat explicitement, et non le supposer.

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
- **Décision** : `docker-compose.yml` à la racine, 5 services — `db` (`pgvector/pgvector:pg16`) et `api` par défaut ; `worker`, `redis`, `front` sous profils. Une seule image Docker, deux rôles via `RUN_AS_WORKER`, exactement comme `render.yaml`.
- **Choix non évidents, et leur raison** :
  - Le worker est **sous profil**, pas par défaut : il s'inscrit auprès de LiveKit Cloud et, avec de vraies credentials, peut réclamer de vrais dispatchs.
  - `redis` est **déclaré mais sous profil** : le contrat de cache n'existe pas encore (ADR-019). Déclarer un service que le code ignore donne l'illusion d'une architecture distribuée — c'est précisément le crime que ce projet s'efforce d'éviter ailleurs.
  - `DATABASE_URL` est surchargée dans `environment:` et pas seulement dans `env_file` : sans surcharge, le conteneur hériterait de l'URL Neon du `.env` local.
  - Deux correctifs `vite.config.ts` ont été nécessaires au service `front` : `strictPort: true` (sinon Vite décale sur 5174 et le CORS du backend, qui n'autorise que 5173, rejette tout en silence) et `VITE_DEV_API_TARGET` (le proxy était codé en dur sur `localhost:8000`, qui désigne le conteneur Vite lui-même).
- **Conséquences** : le dev local se fait sur le même SGBD, avec la même extension vectorielle. En contrepartie, **ce qui ne se teste qu'en production** reste non testé en local : le pooler Neon, l'autoscaling CU, le scale-to-zero, et l'absence de limite mémoire (512 Mo sur Render, aucune ici — une fuite mémoire ne se voit pas en local).
- **⚠️ Statut de vérification** : le YAML est syntaxiquement valide et la topologie a été relue, mais **aucun `docker compose up` n'a été exécuté** — Docker n'est pas installé sur la machine (`docker: command not found`). Ne pas traiter ce fichier comme validé en fonctionnement.
- **Revu si** : le CI passe en conteneurs (le compose devient la base du job d'intégration — à ce moment il doit être testé, pas relu) ; ou si le disque machine ne permet pas de construire l'image (torch + ffmpeg pèsent plusieurs Go, cf. l'alerte disque de 100 %).

---