"""user_roles: rename UserPublicId/RolePublicId to snake_case

Matches the naming convention used by every other column in the schema.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-08
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Renaming a column doesn't touch constraint names — Postgres tracks the
    # constraint definition, not the display name — so the existing FK/PK
    # constraints stay intact and correct after this.
    op.execute('ALTER TABLE identity.user_roles RENAME COLUMN "UserPublicId" TO user_public_id')
    op.execute('ALTER TABLE identity.user_roles RENAME COLUMN "RolePublicId" TO role_public_id')


def downgrade() -> None:
    op.execute('ALTER TABLE identity.user_roles RENAME COLUMN user_public_id TO "UserPublicId"')
    op.execute('ALTER TABLE identity.user_roles RENAME COLUMN role_public_id TO "RolePublicId"')
