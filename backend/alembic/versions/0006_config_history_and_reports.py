"""Add config.config_history and reports.reports

config_history: audit of every zone-config change (old/new JSONB) so config
can be reviewed and restored. reports: generated PDF/Excel report registry —
file itself lives in MinIO, row stores the object key + generation params.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-02
"""
import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS reports")

    op.create_table(
        "config_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("changed_by", UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=True),
        sa.Column("old_config", JSONB, nullable=True),
        sa.Column("new_config", JSONB, nullable=False),
        sa.Column("change_reason", sa.Text, nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        schema="config",
    )
    op.create_index(
        "ix_config_history_zone", "config_history", ["zone_id", "changed_at"], schema="config"
    )

    op.create_table(
        "reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("from_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="Completed"),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        schema="reports",
    )
    op.create_index(
        "ix_reports_enterprise", "reports", ["enterprise_id", "created_on"], schema="reports"
    )


def downgrade() -> None:
    op.drop_index("ix_reports_enterprise", table_name="reports", schema="reports")
    op.drop_table("reports", schema="reports")
    op.drop_index("ix_config_history_zone", table_name="config_history", schema="config")
    op.drop_table("config_history", schema="config")
