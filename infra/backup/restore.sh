#!/bin/bash
# Restores a backup created by backup.sh. DESTRUCTIVE — overwrites the
# current database and MinIO buckets, so it asks for explicit confirmation.
#
# Usage:
#   ./infra/backup/restore.sh <timestamp>   (matches a ./backups/<timestamp>/ dir)
set -euo pipefail

cd "$(dirname "$0")/../.."   # repo root

# Read specific keys as literal text (never `source` .env — values like
# MASTER_PASSWORD_HASH are bcrypt hashes starting with `$2b$`, which the
# shell would otherwise try to expand as positional parameters).
env_var() {
  local val
  val="$(grep -E "^${1}=" .env 2>/dev/null | tail -1 | cut -d'=' -f2-)"
  echo "${val:-$2}"
}
POSTGRES_USER="$(env_var POSTGRES_USER vguser)"
POSTGRES_DB="$(env_var POSTGRES_DB visionguard)"
MINIO_ROOT_USER="$(env_var MINIO_ROOT_USER minioadmin)"
MINIO_ROOT_PASSWORD="$(env_var MINIO_ROOT_PASSWORD minioadmin)"

TIMESTAMP="${1:?Usage: restore.sh <timestamp>  (see ls ./backups/)}"
SRC_DIR="./backups/${TIMESTAMP}"
[ -d "$SRC_DIR" ] || { echo "No backup found at ${SRC_DIR}"; exit 1; }

echo "This will OVERWRITE the current database and MinIO buckets with the"
echo "contents of ${SRC_DIR}. This cannot be undone."
read -r -p "Type 'yes' to continue: " CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "Aborted."; exit 1; }

echo "==> Restoring PostgreSQL..."
docker compose exec -T postgres pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  --clean --if-exists < "${SRC_DIR}/postgres.dump"

echo "==> Restoring MinIO..."
MSYS_NO_PATHCONV=1 docker run --rm --network visionguard_network \
  -v "$(pwd)/${SRC_DIR}/minio:/backup" \
  -e MC_HOST_dst="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000" \
  minio/mc mirror --overwrite /backup dst

echo "==> Restore complete. Restart the backend so it reconnects with a fresh pool: docker compose restart backend"
