"""Multi-role users + role rename

A user can now hold multiple roles at once (e.g. FACTORY_MANAGER +
SAFETY_OFFICER) instead of exactly one — replaces identity.users.role
(single string) with identity.users.roles (JSONB list of strings).

Also renames two role values platform-wide for clarity:
  SUPER_ADMIN -> SYSTEM_ADMIN   (platform team, manages all Enterprises)
  HO_ADMIN    -> ENTERPRISE_ADMIN (manages one Enterprise's factories)
FACTORY_MANAGER, SAFETY_OFFICER, SUPERVISOR, VIEWER are unchanged.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_RENAME = {"SUPER_ADMIN": "SYSTEM_ADMIN", "HO_ADMIN": "ENTERPRISE_ADMIN"}


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("roles", JSONB, nullable=False, server_default="[]"),
        schema="identity",
    )

    # Backfill: each existing single `role` becomes a one-element `roles`
    # array, applying the rename for the two renamed values.
    for old, new in _RENAME.items():
        op.execute(f"""
            UPDATE identity.users SET roles = jsonb_build_array('{new}')
            WHERE role = '{old}'
        """)
    op.execute("""
        UPDATE identity.users SET roles = jsonb_build_array(role)
        WHERE roles = '[]'::jsonb AND role IS NOT NULL
    """)

    op.drop_column("users", "role", schema="identity")


def downgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(50), nullable=True), schema="identity")

    # Best-effort: use the first role in the array, un-renaming it.
    op.execute("""
        UPDATE identity.users SET role = roles->>0 WHERE jsonb_array_length(roles) > 0
    """)
    for old, new in _RENAME.items():
        op.execute(f"UPDATE identity.users SET role = '{old}' WHERE role = '{new}'")

    op.alter_column("users", "role", nullable=False, schema="identity")
    op.drop_column("users", "roles", schema="identity")
