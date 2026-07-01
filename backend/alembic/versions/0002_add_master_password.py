"""Add master_password_hash to identity.users

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("master_password_hash", sa.String(500), nullable=True),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("users", "master_password_hash", schema="identity")
