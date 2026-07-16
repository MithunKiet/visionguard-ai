"""Add missing audit columns dropped-but-not-replaced by 0012

0012's Step 2 dropped several tables' old UUID-typed duplicate audit columns
(ppe_types.created_by, zone_rules.created_by, zone_configs.updated_by,
alerts.created_by) assuming Step 1's `ADD COLUMN IF NOT EXISTS` had already
added the correctly-typed BaseEntity replacement — but IF NOT EXISTS is a
no-op when a same-named column already exists, so on these four tables the
VARCHAR(100) replacement was never added, and the drop left the column
missing entirely.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-08
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_MISSING = [
    (None, "ppe_types", "created_by"),
    ("config", "zone_rules", "created_by"),
    ("config", "zone_configs", "updated_by"),
    ("alerts", "alerts", "created_by"),
]


def _q(schema: str | None, table: str) -> str:
    return f'{schema}.{table}' if schema else table


def upgrade() -> None:
    for schema, table, col in _MISSING:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {col} VARCHAR(100)')


def downgrade() -> None:
    for schema, table, col in _MISSING:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} DROP COLUMN IF EXISTS {col}')
