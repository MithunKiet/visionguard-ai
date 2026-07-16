"""Roles catalog table

Roles were only ever string literals scattered across require_roles(...)
calls in route files — nothing in the database enumerated what roles
exist. This adds a real `roles` table as the canonical reference.

Platform-wide (not enterprise-scoped), unlike ppe_types: every enterprise
shares the same role vocabulary, and the authorization gates
(require_roles() in each route file) hardcode these exact string values —
adding a row here documents/validates against that vocabulary, it doesn't
by itself grant new permissions (that still requires editing the
require_roles() calls in code, since permissions are wired per-endpoint).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_ROLES = [
    ("SYSTEM_ADMIN", "System Administrator", "Platform-wide — manages all Enterprises", "PLATFORM"),
    ("ENTERPRISE_ADMIN", "Enterprise Admin", "Manages one Enterprise and all its factories", "ENTERPRISE"),
    ("FACTORY_MANAGER", "Factory Manager", "Manages one Factory", "FACTORY"),
    ("SAFETY_OFFICER", "Safety Officer", "Investigates alerts and violations within a Factory", "FACTORY"),
    ("SUPERVISOR", "Supervisor", "Manages assigned Zones only", "ZONE"),
    ("VIEWER", "Viewer", "Read-only access within their assigned scope", "ASSIGNED"),
]


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_on", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for code, name, description, scope in _ROLES:
        op.execute(
            "INSERT INTO roles (id, code, name, description, scope, is_active) "
            f"VALUES (gen_random_uuid(), '{code}', '{name}', '{description}', '{scope}', true)"
        )


def downgrade() -> None:
    op.drop_table("roles")
