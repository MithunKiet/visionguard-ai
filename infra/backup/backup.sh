#!/bin/bash
# Verified PostgreSQL + object backup. See docs/BACKUP_RECOVERY.md for environment settings.
set -euo pipefail
cd "$(dirname "$0")/../.."
BACKUP_PYTHON="${BACKUP_PYTHON:-./backend/.venv/bin/python}"
exec "$BACKUP_PYTHON" infra/backup/recovery.py create "$@"
