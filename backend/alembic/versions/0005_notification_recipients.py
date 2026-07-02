"""Add notifications.notification_recipients

Configurable per-zone notification routing: who gets emailed / desktop-
notified when a violation fires in a zone, with a `level` field for future
escalation (Phase 2). zone_id nullable => enterprise-wide fallback recipient.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-02
"""
import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_recipients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("notify_email", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notify_desktop", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_on", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="notifications",
    )
    op.create_index(
        "ix_notification_recipients_enterprise_id",
        "notification_recipients", ["enterprise_id"], schema="notifications",
    )
    op.create_index(
        "ix_notification_recipients_zone_id",
        "notification_recipients", ["zone_id"], schema="notifications",
    )


def downgrade() -> None:
    op.drop_index("ix_notification_recipients_zone_id", table_name="notification_recipients", schema="notifications")
    op.drop_index("ix_notification_recipients_enterprise_id", table_name="notification_recipients", schema="notifications")
    op.drop_table("notification_recipients", schema="notifications")
