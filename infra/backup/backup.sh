#!/bin/bash
# Backs up PostgreSQL (pg_dump, custom format) and MinIO (mc mirror) into
# ./backups/<timestamp>/. Run from anywhere — resolves the repo root itself.
#
# Usage:
#   ./infra/backup/backup.sh
#
# Restore with ./infra/backup/restore.sh <timestamp>  (see ./backups/ for
# available timestamps).
#
# Redis and RabbitMQ are intentionally not backed up — cache and in-flight
# queue state, not durable data; both rebuild themselves from Postgres/live
# traffic after a restore.
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

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="./backups/${TIMESTAMP}"
mkdir -p "$OUT_DIR"

echo "==> Backing up PostgreSQL..."
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -F c \
  > "${OUT_DIR}/postgres.dump"

echo "==> Backing up MinIO (snapshots, logos, reports, models)..."
mkdir -p "${OUT_DIR}/minio"
# MSYS_NO_PATHCONV: Git Bash on Windows otherwise mangles the /backup
# in-container path into a host path before docker even sees it.
MSYS_NO_PATHCONV=1 docker run --rm --network visionguard_network \
  -v "$(pwd)/${OUT_DIR}/minio:/backup" \
  -e MC_HOST_src="http://${MINIO_ROOT_USER}:${MINIO_ROOT_PASSWORD}@minio:9000" \
  minio/mc mirror --overwrite src /backup

echo "==> Done: ${OUT_DIR}"
du -sh "${OUT_DIR}"
