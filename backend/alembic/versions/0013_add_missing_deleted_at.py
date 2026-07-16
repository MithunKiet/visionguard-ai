"""Add missing deleted_at column (BaseEntity audit col omitted by 0012)

0012's _AUDIT_COLS list added is_active/is_approved/created_by/updated_by/
deleted_by/developer_remark to every table, but missed deleted_at — tables
that already soft-deleted via deleted_at (e.g. users) were fine, but tables
that never had it (e.g. worker.ai_workers) are missing a column BaseEntity
requires, breaking any ORM SELECT against them.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-08
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_TABLES = [
    (None, "enterprises"),
    (None, "roles"),
    ("identity", "user_roles"),
    ("identity", "users"),
    ("identity", "refresh_tokens"),
    (None, "factories"),
    (None, "departments"),
    (None, "zones"),
    ("worker", "ai_workers"),
    (None, "cameras"),
    ("config", "zone_configs"),
    (None, "ppe_types"),
    ("config", "zone_rules"),
    ("config", "config_history"),
    ("reports", "reports"),
    (None, "shifts"),
    ("occupancy", "logs"),
    ("ppe", "violations"),
    ("alerts", "alerts"),
    ("alerts", "alert_history"),
    ("notifications", "notification_log"),
    ("notifications", "notification_recipients"),
    ("audit", "audit_log"),
    (None, "camera_maintenance"),
    ("onboarding", "setup_progress"),
]


def _q(schema: str | None, table: str) -> str:
    return f'{schema}.{table}' if schema else table


def upgrade() -> None:
    for schema, table in _TABLES:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE')


def downgrade() -> None:
    for schema, table in _TABLES:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} DROP COLUMN IF EXISTS deleted_at')
