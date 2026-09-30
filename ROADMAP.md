# ROADMAP — Agent Tutor

Plan de réalisation. Chaque lot a un **objectif**, un **périmètre** et un **critère de réussite testable**. Un lot sans critère de réussite n'est pas terminé.

Ordre : **socle → risques → valeur**. Les lots A et B d'abord parce qu'ils protegent tout le reste ; le lot D ensuite parce que sa correction est invisible en local et ne se verra qu'en production.

Statut au 2026-09-29, commit `bba8c36` ; **lot A committé le 2026-09-30**.

---

## Vue d'ensemble

| Lot | Objet | Priorité | Est. |
|---|---|---|---|
| **A** | Gouvernance : écrire et versionner l'architecture | 🔴 | fait, à committer |
| **B** | Durcissement : sécurité, CI, code mort | 🔴 | 1 semaine |
| **C** | Schéma : Alembic, SQL, cohérence | 🔴 | 1 semaine |
| **D** | Cache partagé : Redis | 🔴 | 2-3 jours |
| **E** | Qualité de livraison, dette longue | 🟠 | progressif |

---

## Lot A — Gouvernance · 🔴 · ✅ COMMITTÉ (2026-09-30)

**Objectif** : que la structure du projet soit écrite, versionnée, et lisible par quelqu'un qui n'a jamais vu le code.

| # | Action | Fait |
|---|---|---|
| A1 | `ARCHITECTURE.md` | ✅ |
| A2 | `DECISIONS.md` — ADR consolidés, chaque décision avec son **« Revu si »** | ✅ |
| A3 | `API.md` — routes, auth, format d'erreur | ✅ |
| A4 | `ROADMAP.md` — ce document | ✅ |
| A5 | **Versionner les 4 fichiers + `MEMORY.md`** | ✅ |

**Pourquoi A5 est un vrai lot** : `MEMORY.md` était **gitignoré** et a déjà été vidé une fois par deux writes ratés sur disque plein. Un registre de décisions non versionné n'est pas un registre, c'est une note. Il est temps d'ajouter `MEMORY.md` au suivi git.

**Critère de réussite** : `git log --oneline -- ARCHITECTURE.md DECISIONS.md API.md ROADMAP.md MEMORY.md` retourne au moins un commit.

### A6 — `docker-compose.yml` · ✅ ÉCRIT 2026-09-29 · ⚠️ NON TESTÉ

**Objectif** : rendre le développement local autonome sur le **même SGBD que la production**.

**Pourquoi c'était nécessaire** : le repli SQLite a été retiré le 2026-09-29 (ADR-002). Conséquence directe et non anticipée : le développeur local n'avait plus **aucune** base. Les options restantes étaient Neon depuis la machine — donc écrire sur les données de production en cas d'erreur — ou ne rien faire. Le compose comble ce trou.

**Contenu** — 5 services, 2 par défaut :

| Service | Profil | Rôle |
|---|---|---|
| `db` | *(défaut)* | `pgvector/pgvector:pg16` — même moteur que Neon, extension vectorielle comprise |
| `api` | *(défaut)* | uvicorn, `DATABASE_URL` pointant sur `db`, `AUTH_MODE=dev` |
| `worker` | `voice` | worker LiveKit, **même image**, `RUN_AS_WORKER=1` |
| `redis` | `cache` | cache partagé — **déclaré, pas encore câblé** (lot D) |
| `front` | `full` | Vite en conteneur, sur le réseau Compose |

**Décisions non évidentes, et pourquoi** :
- Le worker est sous profil, pas par défaut : il s'inscrit auprès de **LiveKit Cloud**. Avec de vraies credentials, il peut réclamer de vrais dispatchs et ouvrir une session vocale payante.
- `redis` est sous profil pour la même raison de rigueur : le contrat de cache n'existe pas encore (ADR-019). Déclarer un service que le code ignore crée l'illusion d'une architecture distribuée.
- `DATABASE_URL` est surchargée dans `environment:`, pas seulement dans `env_file` — sans ça, le conteneur pointerait sur la **base Neon de production** depuis la machine du développeur.
- `strictPort: true` ajouté à `vite.config.ts` : sinon Vite bascule sur 5174 si 5173 est occupé, et le CORS du backend (qui n'autorise que 5173) rejette tout en silence.
- `VITE_DEV_API_TARGET` ajouté à `vite.config.ts` : le proxy était codé en dur sur `localhost:8000`, qui désigne le conteneur Vite lui-même et non le backend.

**⚠️ Non vérifié** : Docker n'est pas installé sur la machine de développement (`docker: command not found`). Le YAML est validé syntaxiquement, la topologie est lue deux fois, mais **aucun `docker compose up` n'a été exécuté**. Ce n'est pas un fichier « écrit et testé », c'est un fichier « écrit et relu ».

**Critère de réussite** : `docker compose up -d` puis `curl localhost:8000/api/health` renvoie 200 et `curl localhost:8000/api/health/ready` confirme la connexion Postgres. **À faire à la première machine disposant de Docker.**

---

## Lot B — Durcissement · 🔴

### B1 — CORS : une seule source de vérité · ✅ FAIT 2026-09-29

**Objectif** : que la politique CORS soit décidée à un seul endroit, le backend.

**Fait** : `vercel.json` déclarait `Access-Control-Allow-Origin: *` sur `/api/(.*)`.

**Correction appliquée** : le bloc `headers` `/api/(.*)` a été retiré de `vercel.json`. Il ne reste qu'un bloc d'en-têtes de sécurité (nosniff, frame-deny, xss).

**Ce que l'analyse a révélé, et qui change la priorité** : ces en-têtes s'appliquaient à l'origine **Vercel**, alors que le trafic de production ne passe **pas** par Vercel. `frontend/.env.production:14` fixe `VITE_API_URL=https://agent-tutor-api.onrender.com`, et `src/api/base.ts:14` en fait `BASE` — le navigateur appelle donc **Render directement**, en cross-origin. Ces en-têtes étaient donc **inertes sur le chemin réel** : les supprimer ne change aucun comportement, et ce n'était pas le bug. Le vrai problème est B2.

**Critère de réussite** : `curl -sI https://<front>/api/health | grep -i access-control` ne renvoie pas `*`. · **Statut** : vérifié sur le fichier (`headers: 1`, JSON valide).

### B1bis — Trancher le mode de transport de l'API · 🟠 EN ATTENTE DE DÉCISION

Le dépôt contient **deux stratégies concurrentes**, non documentées comme mutuellement exclusives.

| | `VITE_API_URL` | Qui applique le CORS | Statut |
|---|---|---|---|
| **A — proxy Vercel** | vide → URL relatives | personne (même origine) | rewrite `/api/:path*` de `vercel.json` **vivant** |
| **B — direct Render** | `https://agent-tutor-api.onrender.com` | `CORSMiddleware` backend, via `ALLOWED_ORIGINS` | **c'est ce qu'est committé** |

Le dépôt est committé en **B**, mais `ALLOWED_ORIGINS` sur Render est en A-valeur (`localhost:5173`). Les deux ne peuvent pas être vrais en même temps.

**Conséquence mesurable** : `src/api/events.ts:12` fait `new EventSource('/api/events')` en **URL relative**, donc relative à l'origine Vercel — elle est la seule route qui ne respecte pas `BASE`. En mode B, tout le reste va vers Render et le flux SSE passe par le proxy : **deux origines dans la même application**.

**Décision attendue** : trancher A ou B, puis aligner les trois fichiers (`frontend/.env.production`, `vercel.json`, `backend/render.yaml`) sur le même choix. Tant que ce n'est pas fait, « corriger le CORS » n'a pas de sens.

### B2 — `ALLOWED_ORIGINS` en production · ✅ VÉRIFIÉ CORRECT 2026-09-29 · fichier corrigé

**Objectif** : que la valeur documentée dans `render.yaml` soit celle qui répond réellement en production.

**Ce que j'avais écrit, et pourquoi c'était faux** : j'avais identifié `ALLOWED_ORIGINS=http://localhost:5173` comme un **bloquant de production**. C'est une lecture du **fichier**, pas de l'état déployé. Or `render.yaml:3-7` dit lui-même que le dashboard prime sur le fichier.

**Vérification en production** (`curl -H "Origin: …"` contre `https://agent-tutor-api.onrender.com/api/health`) :

| Origine testée | Réponse | Verdict |
|---|---|---|
| `https://frontend-sigma-lilac-62.vercel.app` | `200` + `access-control-allow-origin: https://frontend-sigma-lilac-62.vercel.app` | ✅ accepté |
| `http://localhost:5173` | `200` + `access-control-allow-origin: http://localhost:5173` | ✅ accepté |
| `https://evil.example.com` | `200` **sans** en-tête ACAO | ✅ refusé par le navigateur |

**Conclusion** : la production **n'est pas cassée**. Le dashboard Render porte la bonne liste. Le défaut était documentaire : `render.yaml` décrivait une valeur qui, si elle avait été appliquée par un `blueprint apply`, aurait cassé l'application entière.

**Correction appliquée** : `render.yaml` porte désormais la valeur vérifiée — `https://frontend-sigma-lilac-62.vercel.app,http://localhost:5173,http://127.0.0.1:5173`.

**Effet de bord à connaître** : Starlette ne gère pas les jokers, donc les **déploiements de prévisualisation Vercel** (`frontend-<hash>.vercel.app`) sont refusés. Tester une branche en preview exige d'ajouter son domaine explicitement. Le retirer de la liste dès que le projet n'en a plus besoin.

**Critère de réussite** : les trois lignes du tableau ci-dessus restent vraies après le prochain déploiement. · **Statut** : vérifié en ligne, pas supposé.

### B3 — Ne pas versionner les dumps d'API · ✅ FAIT 2026-09-29

**Objectif** : qu'aucun secret ne puisse être committé par accident.

**Correction appliquée** — `.gitignore` étendu de 7 l. à 30 l. : dumps d'API (`proj-neon.json`, `svc_raw.json`, `backend/authcfg.json`, `backend/create.json`), secrets OAuth Google (`backend/data/mcp/google/`), checkpoints LangGraph locaux (`backend/.langgraph_api/`), base SQLite abandonnée (`backend/database/`, `*.db`), logs (`logs/`), sessions agent (`.zcode/`).

**Vérification du contenu avant d'ignorer** — aucun secret actif trouvé :
- `proj-neon.json` (1 410 o) : métriques d'un projet Neon, aucun secret
- `svc_raw.json` (4 776 o) : dump de l'API Render, `envVars: []` sur les 4 services — **aucune valeur de variable d'environnement exposée**
- `backend/authcfg.json` : URLs JWKS et base Neon Auth, déjà committées dans `frontend/.env.production` — publiques par construction
- `backend/create.json` : message d'erreur provisioning, aucun secret

→ **Aucune rotation nécessaire.** En revanche `backend/data/mcp/google/client_secret*.json` est un vrai secret OAuth (client Google), jamais committé, désormais couvert.

**Critère de réussite** : `git check-ignore` renvoie `IGNORE` pour les 7 cibles. · **Statut** : vérifié, 7/7.

### B4 — Rate limiting sur les routes coûteuses

**Objectif** : qu'un appel non authentifié ne puisse pas déclencher une facture LLM.

**Fait** : aucun rate limiting. `POST /api/chat` déclenche un LLM, `POST /api/livekit/token` déclenche une session.

**Périmètre** : limiter `POST /api/chat`, `GET /api/chat/stream`, `POST /api/livekit/token`, `POST /api/livekit/agent/start`. Limite par `user_id` résolu depuis le token, pas par IP — une IP partagée (entreprise, lycée) ne doit pas pénaliser un utilisateur. Le rate limiter à mémoire distributed **dépend du lot D** : s'il est local, il a le même défaut que le cache actuel.

**Critère de réussite** : une série de 10 requêtes au-delà du quota renvoie 429, et le compteur est partagé entre l'API et le worker.

### B5 — Rétablir le blocage de la CI, par étapes

**Objectif** : que la CI protège à nouveau la production, sans re-bloquer pour des raisons d'infrastructure.

**Fait** : `continue-on-error: true` sur `pytest` **et** sur `oxlint`. Seuls `compileall` et le build Vite bloquent.

**Périmètre** — par étapes, chacune vérifiable séparément :
1. `npm ci` doit réussir. **Action préalable** : vérifier que `package-lock.json` est cohérent avec `package.json` (`npm ci` échoue sur un lock désynchronisé — un problème signalé le 2026-09-26 et jamais vérifié depuis).
2. Lint bloquant, en traitant d'abord les findings qui sont des faux positifs.
3. `pytest` bloquant sur les suites **non régressives** seulement. Sont exclues, et c'est assumé : `test_phase2_activity.py`, `test_phase2_evaluation.py` (scripts legacy avec `sys.exit`, qui provoquent un `INTERNALERROR` sous pytest) et les tests réseau (`test_auth_security.py`, `test_final_integration.py`, qui exigent un serveur local).

**Critère de réussite** : un commit qui casse volontairement un test non régressif **échoue** la CI, et un commit qui casse le lint **échoue** la CI.

### B6 — Supprimer le code mort

**Objectif** : que le code soit ce qui est exécuté.

**Fait** : voir `DECISIONS.md` ADR-002 pour le détail.

| Cible | Pourquoi c'est mort |
|---|---|
| ~~`app/graph/main.py` (350 o)~~ **supprimé 2026-09-29** | **Un package du même nom existe** (`app/graph/main/`). Python résout toujours le package : ce fichier n'était **jamais** exécuté. Sa docstring disait « SUPPRESSION prévue phase cleanup (§30) » — la phase a eu lieu, le fichier est resté. |
| ~~`app/graph/state.py` (301 o)~~ **supprimé 2026-09-29** | Idem, shadowé par `app/graph/main/state.py` |
| Branche SQLite de `_build_engine()`, `_sqlite_url()`, `get_checkpoint_engine()`, `CHECKPOINTS_DB_PATH` | Le startup lève si `DATABASE_URL` est absente (ADR-002) — la branche est inatteignable |
| ~150 lignes SQLite de `services/documents/vector_store.py` | Idem |
| Branche `"SQLite"` de `graph/main/graph.py:284` | `is_postgres_persistence()` retourne toujours `True` |
| `TTLCache.get_or()` (`ttl.py:71-73`) | Double appel à `get()`, aucun appelant (ADR-019) |
| `langgraph-checkpoint-sqlite` (`requirements.txt:19`) | Dépendance de l'époque SQLite ; plus aucun `SqliteSaver` dans le code |

> ⚠ **La CI ne peut pas détecter `app/graph/main.py`** : `python -c "import app.graph.main"` résout le **package**, donc l'import passe. C'est exactement le genre de code mort que le smoke test ne voit pas.

**Preuve que la suppression est sans effet** — 8 fichiers font `from app.graph.main import get_agent` : `app/main.py:9`, `app/config.py:399`, `app/api/activity.py:82`, `app/infrastructure/livekit/transcript.py:22`, `app/services/activity/store.py:32,117`, `app/services/agent/runner.py:93,163,428,589`. Or `get_agent` **n'existe pas** dans le shim : si le shim était résolu, ces 8 imports lèveraient `ImportError`. L'application tourne en prod → le shim n'a jamais été résolu.

**Suppression vérifiée le 2026-09-29** : après `git rm`, `from app.graph.main import get_agent, compile_main_graph, MainState, build_graph` et `from app.graph.main.state import CustomAgentState` importent correctement — le package exporte ces 5 symboles via `app/graph/main/__init__.py`.

**Critère de réussite** : `grep -rn "app.graph.main" backend/ --include=*.py` ne retourne que des références au package, et la suite de tests passe à l'identique avant/après. · **Statut** : moitié fait (les 2 shims). La branche SQLite de `vector_store.py` et la dépendance `langgraph-checkpoint-sqlite` restent.

### B7 — Une seule dépendance d'administration

**Objectif** : qu'une règle de sécurité ait un nom.

**Fait** : trois noms pour le même contrôle — `require_admin` (`app/auth/resolver.py:299`), `verify_admin_auth` (`app/api/admin/observability.py:35`, qui délègue), `get_current_admin_user` (qui n'est qu'un **alias importé** de `require_admin`, `app/api/admin/dashboard.py:15`). La sécurité n'est pas en jeu ; l'audit, oui.

**Périmètre** : ne garder que `require_admin`. Supprimer les deux autres noms.

**Critère de réussite** : `grep -rn "verify_admin_auth\|get_current_admin_user" backend/` ne retourne rien.

### B8 — Trancher les deux renommages en attente

**Objectif** : que les pièges signalés depuis trois mois soient fermés.

| Décision | Options | Coût |
|---|---|---|
| `ADMIN_EXTERNAL_IDS` | Le renommage est **fait** (`app/config.py:119-123`) avec repli sur l'ancien nom. Reste à décider **quand retirer le repli** | Vérifier que `ADMIN_EXTERNAL_IDS` est posée sur **tous** les environnements, puis retirer `ADMIN_CLERK_IDS` |
| `clerk_user_id` | Renommer en `external_user_id`, ou conserver | Migration sur la base Neon live + index unique partiel `idx_users_clerk` (`connections.py:103-117`) |

**Périmètre** : décider, écrire la décision dans `DECISIONS.md` (superseder ADR-017 et ADR-018), puis exécuter. Le bon moment pour la colonne est **le lot C**, puisqu'il y aura une migration.

**Critère de réussite** : chaque nom obsolète a soit disparu du code, soit une raison écrite de rester.

---

## Lot C — Schéma · 🔴

### C1 — Alembic

**Objectif** : que le schéma ait un historique, une version, et un rollback.

**Fait** : aucun système de migration. `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` inline, exécutés au startup (`infrastructure/database/schema.py:311`). Vérifié : pas de dossier `migrations`, pas de `alembic.ini`.

**Périmètre** :
1. Installer Alembic et le driver PostgreSQL (asyncpg ou psycopg).
2. Générer un **baseline** qui décrit le schéma actuel **tel qu'il est**, sans le modifier. L'erreur classique est de faire le baseline sur une base vide et de recréer les tables à l'identique alors qu'elles ont déjà Drifté.
3. Vérifier le baseline contre la base Neon **avant** de le committer : `alembic check` doit ne remonter aucun écart.
4. Passer toute évolution future par `alembic revision`.
5. `init_schema()` reste pendant la transition, puis perd son rôle.

**Critère de réussite** : `alembic current` ne signale aucun écart sur la base de production, et une migration de test s'applique puis s'annule proprement.

### C2 — Vérifier la santé de la base au démarrage, pas seulement à la demande

**Objectif** : qu'un problème de connexion soit détecté au démarrage, pas à la première requête utilisateur.

**Critère de réussite** : `GET /api/health/ready` renvoie 503 quand la base est injoignable, et le healthcheck Render bascule.

### C3 — Rendre visible le repli lexical

**Objectif** : savoir si la qualité de retrieval se dégrade.

**Fait** : ADR-014 prévoit un repli sur la recherche lexicale quand le store vectoriel tombe. Il n'y a **aucune métrique** indiquant que ce repli se produit.

**Périmètre** : un compteur ou un niveau de log dédié. Le RAG est la fonctionnalité centrale du produit ; une dégradation silencieuse est pire qu'une panne visible.

**Critère de réussite** : le repli est visible dans `/api/admin/monitoring/summary` sans avoir à lire les logs.

### C4 — Ramener le SQL dans les repositories

**Objectif** : que la frontière de couches soit réelle, et pas seulement documentée.

**Fait** : 13 fichiers écrivent du SQL en dehors de `repositories/` et `infrastructure/database/` :
`api/admin/dashboard.py` · `api/admin/monitoring.py` · `graph/subgraphs/video/persist.py` · `infrastructure/database/{connections,schema,threads,users,videos}.py` · `logging/events.py` · `services/documents/vector_store.py` · `services/knowledge/{resolver,store}.py` · `services/storage/{calendar_events,mcp_files,object_store}.py`

**Périmètre** : **un seul fichier à la fois**, du plus court au plus long. Les quatre fichiers `infrastructure/database/` sont à leur place et n'ont pas vocation à bouger.

**Critère de réussite** : `grep -rln "SELECT\|INSERT\|UPDATE\|DELETE" backend/app/api/` ne retourne aucun fichier.

### C5 — Renommer `clerk_user_id` (si B8 l'a décidé)

À faire **dans la même fenêtre** que C1, pour ne pas payer deux migrations. Décision à `DECISIONS.md` ADR-017.

---

## Lot D — Cache partagé · 🔴

**Objectif** : que l'API et le worker vocal voient la même donnée au même moment.

**Fait** : ADR-006bis. La séquence du défaut est décrite dans `ARCHITECTURE.md` §6.2. En une phrase : l'API invalide le cache, le worker garde l'ancien profil **5 minutes**, sans log et sans erreur — et **invisible en développement local**.

### D1 — Définir le contrat, pas le fournisseur

**Périmètre** : l'interface `TTLCache` reste le contrat. Corriger d'abord les deux défauts qui la rendent inexploitable en Redis (ADR-019) :
- `get_or()` — bug de double appel, aucun appelant → **supprimer**.
- `clear_prefix()` — aucun appelant, et **pas d'équivalent Redis** (`SCAN` + `DEL` est nettement plus cher qu'un `DEL` sur motif) → ne pas promettre ce contrat.

Le code ne doit dépendre que de l'API Redis, jamais du SDK d'un fournisseur. C'est ce qui rend le changement de fournisseur gratuit.

### D2 — Remplacer l'implémentation in-process

**Périmètre** : implémentation Redis derrière la même interface. Fournisseur : **Upstash** (offre gratuite 256 Mo / 500 K commandes par mois / 10 000 cmd/s, sans carte bancaire).

Trois caches à convertir, dans cet ordre de valeur :
1. `mem:{user_id}:profile` et `mem:{user_id}:facts` — **le seul qui produit le défaut observable**.
2. `subjects:registry` — invalidé à l'écriture, donc peu de trafic.
3. Engine knowledge (`lru_cache`) — **ne rien faire**, c'est un singleton immuable, le transformer serait du bruit.

### D3 — Trancher l'invalidation par motif

**Périmètre** : décider si `clear_prefix` est réellement nécessaire. Si oui, concevoir le contrat explicitement pour Redis. Si non, le supprimer de l'interface. **Ne pas laisser une promesse que l'implémentation ne peut pas tenir.**

### D4 — Mesurer avant de payer

**Objectif** : savoir si le cache sert.

`log_event("MEMORY_READ", extra={"cached": True})` existe déjà (`services/memory/memory.py:446-458`) mais **n'est agrégé nulle part**. Upstash facture **par commande** : un cache qui fonctionne est un cache qui racks up commands.

**Critère de réussite** : le taux de hit est exposé dans `/api/admin/monitoring/stats` avant le passage en PAYG.

### D5 — Vérifier le seuil de bascule

**Critère de réussite** : le volume de commandes est mesuré sur une semaine réelle. Si l'offre gratuite est atteinte de façon récurrente, basculer sur **Layerbase Solo (5 $/mois, prix fixe, commandes non facturées, API REST identique)**. Upstash Fixed 250 Mo à 10 $/mois reste le repli classique.

### D6 — Rendre le rate limiting compatible (dépend de B4)

Le rate limiter doit être **partagé** entre l'API et le worker, pour la même raison que le cache. Un limiteur local, c'est un limiteur contournable.

---

## Lot E — Qualité de livraison · 🟠

Continu, sans échéance.

| # | Action | Pourquoi |
|---|---|---|
| E1 | Contrôler les `except Exception` (196 occurrences) | Aux frontières (nodes LangGraph, tool handlers) c'est justifié et documenté. Ailleurs, c'est une exception avalée. Ne pas faire de purge globale : traiter au fil des fichiers touchés. |
| E2 | Résoudre les ~20 fichiers `compatibilit\|shim\|legacy\|deprecated` | Un par un, jamais en une passe. |
| E3 | Unifier les 3 dossiers UI front (`src/assistant-ui/`, `src/components/assistant-ui/`, `src/components/agents-ui/`) | Le lot le plus risqué du roadmap front : la suppression d'un dossier ne peut pas se faire à l'aveugle. **Commencer par établir lequel est réellement importé** — `grep` sur les imports, pas sur la taille. |
| E4 | Trancher le sort des 3 fichiers WIP déclarés non committables | `MEMORY.md` les liste. Les terminer, ou les retirer définitivement du dépôt. |
| E5 | Décider du sort des routes dupliquées | `/chat` → redirect vers `/assistant` ; `ProfilePage` en racine alors que `/settings/profile` existe. |
| E6 | Versionner la configuration modèle dans git | `models.yaml` est écrit par l'API d'administration. Deux déploiements peuvent le modifier différemment. |
| E7 | Trancher la versionnement de l'API | Aujourd'hui aucun. acceptable tant qu'il n'y a pas de client tiers. |

---

## Ce qu'il ne faut **pas** faire

- **Ne pas introduire de microservices.** Le projet a deux services pour une raison précise et documentée (RAM), pas par manque de découpage.
- **Ne pas mettre en cache les résultats LLM ni les états de thread.** Le checkpointer Postgres est la seule source de vérité (ADR-007).
- **Ne pas faire de migration de schéma sans baseline vérifié** contre la base réelle. C'est le geste qui détruit une base de production.
- **Ne pas restaurer le blocage de la CI d'un coup.** Trois poussées consécutives ont cassé la production. Le blocage se rétablit par étapes, avec un jalon vérifiable à chaque fois.
- **Ne pas supprimer du code sur la foi d'une liste de « modules jamais importés »** produite par une analyse automatique : cette liste contient des faux positifs connus.
