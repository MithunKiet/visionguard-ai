"""User-roles junction table

Replaces identity.users.roles (a JSONB array with no referential
integrity — nothing stopped it holding a role that doesn't exist) with a
proper many-to-many: identity.user_roles(user_id, role_code), FK'd to both
identity.users and roles(code).

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("identity.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_code", sa.String(50), sa.ForeignKey("roles.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_on", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_code", name="uq_user_roles_user_role"),
        schema="identity",
    )

    # Migrate each JSONB roles array entry into its own row.
    op.execute("""
        INSERT INTO identity.user_roles (id, user_id, role_code)
        SELECT gen_random_uuid(), u.id, r.role_code
        FROM identity.users u, jsonb_array_elements_text(u.roles) AS r(role_code)
    """)

    op.drop_column("users", "roles", schema="identity")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("roles", JSONB, nullable=False, server_default="[]"),
        schema="identity",
    )
    op.execute("""
        UPDATE identity.users u SET roles = (
            SELECT COALESCE(jsonb_agg(ur.role_code), '[]'::jsonb)
            FROM identity.user_roles ur WHERE ur.user_id = u.id
        )
    """)
    op.drop_table("user_roles", schema="identity")
