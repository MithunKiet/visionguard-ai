"""Drop unused master_password_hash from identity.users

Per-user master password was replaced by a system-level MASTER_PASSWORD_HASH
env var. This column is no longer used.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-01
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "master_password_hash", schema="identity")


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column(
        "users",
        sa.Column("master_password_hash", sa.String(500), nullable=True),
        schema="identity",
    )
