#!/usr/bin/env bash
# Sauvegarde PostgreSQL + volume ClickHouse de la stack Langfuse locale.
#
#   Usage :  ./backup.sh
#   Sortie :  ./backups/langfuse-pg-<horodatage>.dump
#             ./backups/langfuse-clickhouse-<horodatage>.tar.gz
#
#   NB : ce script concerne le mode « docker compose local ».
#   En déploiement Render (Blueprint langfuse4-template), les sauvegardes
#   sont assurées par Render : activer les sauvegardes managées PostgreSQL
#   et vérifier la persistance des disques ClickHouse/MinIO (voir README).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"

# ---------------------------------------------------------------------------
# 1. PostgreSQL — dump binaire compressé (pg_dump custom format)
# ---------------------------------------------------------------------------
POSTGRES_USER="${POSTGRES_USER:-postgres}"
echo "==> Sauvegarde PostgreSQL (user: ${POSTGRES_USER})..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc -d postgres \
  > "$BACKUP_DIR/langfuse-pg-${STAMP}.dump"
echo "    OK : $BACKUP_DIR/langfuse-pg-${STAMP}.dump"

# ---------------------------------------------------------------------------
# 2. ClickHouse — archive tar.gz du volume de données
#    Le nom du volume dépend du préfixe du projet compose (« name: langfuse ») :
#    on le détecte au lieu de le deviner.
# ---------------------------------------------------------------------------
CLICKHOUSE_VOLUME="$(docker volume ls -q | grep 'clickhouse_data' | head -1 || true)"
if [ -z "$CLICKHOUSE_VOLUME" ]; then
  echo "ERREUR : volume ClickHouse 'clickhouse_data' introuvable — stack démarrée ?" >&2
  exit 1
fi
echo "==> Sauvegarde ClickHouse (volume: ${CLICKHOUSE_VOLUME})..."
docker run --rm \
  -v "${CLICKHOUSE_VOLUME}:/data:ro" \
  -v "$(pwd)/${BACKUP_DIR}:/backup" \
  alpine tar czf "/backup/langfuse-clickhouse-${STAMP}.tar.gz" -C /data .
echo "    OK : $BACKUP_DIR/langfuse-clickhouse-${STAMP}.tar.gz"

echo
echo "Sauvegarde terminée. Conserver ces fichiers hors de la machine"
echo "(ex. bucket S3 privé, stockage externe chiffré), jamais dans le dépôt git."