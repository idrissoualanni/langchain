#!/usr/bin/env bash
# Génère les secrets Langfuse pour infra/langfuse/.env
#
#   Usage :  ./generate-secrets.sh > .env
#   Puis  :  éditer .env pour renseigner l'email admin
#            (LANGFUSE_INIT_USER_EMAIL) et, si besoin, NEXTAUTH_URL.
#
# Pourquoi openssl rand -hex et PAS base64 :
#   - base64 produit des caractères +/-/= qui cassent les URL de connexion
#     PostgreSQL et peuvent casser le parsing des variables.
#   - hex ne produit que [0-9a-f].
#
# Exécuter en bash (Git Bash sous Windows, bash sous Linux/macOS).
set -euo pipefail

# Garde-fou : ne jamais écraser un .env existant par erreur.
# NB : -s (non vide) car la redirection `> .env` crée déjà un fichier vide avant
# l'exécution du script ; -f déclencherait une fausse erreur à chaque fois.
if [ -s .env ]; then
  printf "ERREUR : .env existe deja. Bouge-le d'abord (mv .env .env.bak).\n" >&2
  exit 1
fi

# Le mot de passe Postgres est utilisé DANS DATABASE_URL : une seule source.
POSTGRES_PASSWORD="$(openssl rand -hex 32)"

printf '# Langfuse v4 — secrets générés le %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '# ATTENTION : renseigner LANGFUSE_INIT_USER_EMAIL avant le premier démarrage.\n'
printf '# Ne jamais committer ce fichier.\n\n'

printf 'POSTGRES_PASSWORD=%s\n'   "$POSTGRES_PASSWORD"
printf 'CLICKHOUSE_PASSWORD=%s\n' "$(openssl rand -hex 32)"
printf 'REDIS_AUTH=%s\n'          "$(openssl rand -hex 32)"
printf 'MINIO_ROOT_PASSWORD=%s\n' "$(openssl rand -hex 32)"
printf 'NEXTAUTH_SECRET=%s\n'     "$(openssl rand -hex 32)"
printf 'SALT=%s\n'                "$(openssl rand -hex 32)"
printf 'ENCRYPTION_KEY=%s\n'      "$(openssl rand -hex 32)"

printf 'DATABASE_URL=postgresql://postgres:%s@postgres:5432/postgres\n' "$POSTGRES_PASSWORD"

# Clés d'API du projet (préfixes Langfuse officiels pk-lf-/sk-lf-)
printf 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-%s\n' "$(openssl rand -hex 16)"
printf 'LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-%s\n' "$(openssl rand -hex 16)"
# Mot de passe du compte admin initial (à remplacer si tu préfères)
printf 'LANGFUSE_INIT_USER_PASSWORD=%s\n' "$(openssl rand -hex 16)"