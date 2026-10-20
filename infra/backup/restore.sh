#!/bin/bash
# Isolated drill only: creates new destinations, never overwrites the running database.
# See docs/BACKUP_RECOVERY.md. Legacy destructive timestamp-only restores are removed.
set -euo pipefail
cd "$(dirname "$0")/../.."
BACKUP_PYTHON="${BACKUP_PYTHON:-./backend/.venv/bin/python}"
exec "$BACKUP_PYTHON" infra/backup/recovery.py drill "$@"
