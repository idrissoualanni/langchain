# Langfuse v4 — auto-hébergé (Agent Tutor)

Observabilité LLM pour l'agent. Deux modes :
1. **Blueprint Render** (recommandé, sans VPS) — Langfuse est déployé sur Render via le
   template communautaire officiel `render-examples/langfuse4-template`.
2. **Docker compose local** — ce dossier, pour tester / reproduire la même configuration
   en local avant (ou sans) la mise en production.

Version épinglée : **4.48.0** (web + worker). SDK backend : `langfuse==4.16.0`.

> Contenu : `docker-compose.yml` (6 services), `.env.example`, `generate-secrets.sh`,
> `backup.sh`, `Caddyfile.example` (optionnel VPS), ce README.
> **Aucun secret n'est committé** : tout passe par `.env` (gitignoré).

---

## 1. Déploiement sur Render (recommandé)

Le [template](https://render.com/deploy-template/api/github/start?template_repo=langfuse4-template)
crée sur ton compte Render :

| Ressource | Type |
|---|---|
| langfuse-web + langfuse-worker | services Render |
| PostgreSQL 18 | base managée |
| Redis (Key Value) | managé |
| ClickHouse | service privé + disque persistant |
| MinIO | service public + disque persistant (URLs média presignées) |

Fermer « Deploy to Render » : la page du template permet (avant d'appliquer) de choisir
les plans de service et tailles de disque — sélectionner en fonction de la charge attendue.
**Configurer les sauvegardes avant tout trafic de production** (sauvegardes managées
PostgreSQL côté Render + snapshot des disques ClickHouse/MinIO).

Il s'agit d'un template **communautaire** maintenu hors de l'organisation Langfuse :
support best-effort, à vérifier à chaque mise à jour.

### Configuration après déploiement (variables d'environnement du service web)

Dans le dashboard Render, service `langfuse-web` → *Environment* :

- `AUTH_DISABLE_SIGNUP=true` — désactive l'inscription ouverte (seuls les comptes déjà
  créés se connectent).
- `LANGFUSE_ALLOWED_ORGANIZATION_CREATORS=` *(vide)* — interdit la création d'organisations.
- `LANGFUSE_INIT_ORG_ID=agent-tutor`, `LANGFUSE_INIT_ORG_NAME=Agent Tutor`,
  `LANGFUSE_INIT_PROJECT_ID=agent-tutor-prod`, `LANGFUSE_INIT_PROJECT_NAME=Agent Tutor (prod)`,
  `LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-…`, `LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-…`,
  `LANGFUSE_INIT_USER_EMAIL=<ton email>`, `LANGFUSE_INIT_USER_NAME=Admin`,
  `LANGFUSE_INIT_USER_PASSWORD=<mot de passe fort>`.
  (Initialisation automatique org + projet + clés + compte admin au premier démarrage —
  ne **pas** quoter les valeurs, piège doc issue #3398.)
- `NEXTAUTH_URL=https://<ton-instance>.onrender.com` (l'URL HTTPS fournie par Render).
- `TELEMETRY_ENABLED=false`.

> **À noter** : l'URL de l'interface est celle de Render (`https://<ton-instance>.onrender.com`),
> c'est cette valeur que le backend utilisera pour `LANGFUSE_BASE_URL`.

---

## 2. Docker compose local (test / reproduction)

### Prérequis
- Docker 24+ avec `docker compose` v2.
- ~8 Go de RAM libre pour la stack.
- Bash (Git Bash sous Windows, bash natif sous Linux/macOS).

### Démarrage
```bash
cd infra/langfuse

# 1) Générer les secrets (n'écrase jamais un .env existant)
./generate-secrets.sh > .env

# 2) Renseigner l'email admin dans .env
#    LANGFUSE_INIT_USER_EMAIL=ton@email.fr   (et, si besoin, NEXTAUTH_URL)

# 3) Démarrer
docker compose up -d

# 4) Vérifier la santé (attendre ~30-60 s le premier démarrage)
docker compose ps
curl -s http://localhost:3000/api/public/health   # → OK
curl -s http://localhost:3000/api/public/ready    # → OK (readiness)
```

Interface : http://localhost:3000 — se connecter avec l'email admin créé par l'init
headless. Les clés du projet (publiées dans `LANGFUSE_INIT_PROJECT_*`) sont à reporter
dans `backend/.env` (section `LANGFUSE OBSERVABILITY`).

### Arrêt
```bash
docker compose down            # arrête les conteneurs (données conservées)
# NE JAMAIS lancer : docker compose down -v   ← détruit les volumes (données perdues)
```

### Mise à jour
```bash
cd infra/langfuse
# Vérifier la dernière version : https://hub.docker.com/r/langfuse/langfuse/tags
# Éditer docker-compose.yml (2 lignes : image langfuse-web + langfuse-worker),
# puis :
docker compose pull
docker compose up -d
# Vérifier les migrations (logs du web/worker, /api/public/ready) et l'UI.
```
Toujours sauvegarder avant une mise à jour (`./backup.sh`).

### Vérification complète
```bash
docker compose ps                    # tous les services "healthy"
curl -s http://localhost:3000/api/public/ready   # readiness
docker compose logs -f langfuse-web  # journaux (en cas de problème de démarrage)
```

---

## 3. Sauvegarde / restauration (mode compose local)

```bash
./backup.sh
# Produit : backups/langfuse-pg-<horodatage>.dump (PostgreSQL)
#           backups/langfuse-clickhouse-<horodatage>.tar.gz (ClickHouse)
```
Conserver ces fichiers **hors de la machine et hors du dépôt git** (S3 privé, coffre, etc.).

### Restauration PostgreSQL
```bash
# La stack doit être arrêtée pour éviter toute écriture concurrente :
docker compose down
# Restaurer dans un conteneur Postgres temporaire (volume "vierge" requis) :
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U postgres -d postgres --clean --if-exists < backups/langfuse-pg-<horodatage>.dump
# Puis démarrer le reste : docker compose up -d
```

### Restauration ClickHouse
```bash
# Arrêter la stack, supprimer/renommer le volume clickhouse_data, puis :
docker run --rm \
  -v <nom_volume_clickhouse_data>:/data \
  -v "$(pwd)/backups:/backup" \
  alpine tar xzf /backup/langfuse-clickhouse-<horodatage>.tar.gz -C /data
# Redémarrer : docker compose up -d
```

---

## 4. Réseau et sécurité

- Seuls `langfuse-web` (3000) et `minio` (9090) sont exposés.
- MinIO est **public** (port 9090) car Langfuse génère des URLs média presignées pour
  les navigateurs/SDK — recommandation officielle ; les requêtes restent signées.
- Tous les autres services (worker 3030, ClickHouse 8123/9000, Redis 6379, Postgres 5432,
  console MinIO 9091) sont liés à `127.0.0.1`.
- Inscription ouverte désactivée : `AUTH_DISABLE_SIGNUP=true`.
- Création d'organisations restreinte : `LANGFUSE_ALLOWED_ORGANIZATION_CREATORS` (vide = aucune).
- Version majeure : **v4** — modèle de données « observations-first » (ClickHouse obligatoire).

### Si un jour tu bascules sur un VPS + domaine
- `Caddyfile.example` fourni : Caddy termine le HTTPS et proxie `langfuse-web:3000`.
  Renseigner alors `NEXTAUTH_URL=https://langfuse.<domaine>` et `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT`.

---

## 5. Dépendance avec le backend (Agent Tutor)

Le backend envoie les traces via le SDK Python `langfuse==4.16.0` avec :
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (clés du projet, générées par l'init headless)
- `LANGFUSE_BASE_URL` (URL de l'instance Render ou `http://localhost:3000` localement)
- `LANGFUSE_ENABLED` (interrupteur global ; le client SDK se désactive aussi seul si clés absentes)

Voir `backend/app/observability/langfuse.py` (Volet B).