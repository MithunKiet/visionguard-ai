"""Corrective plans, due dates and immutable photo evidence for incidents."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    for column in [sa.Column("action_description", sa.Text()), sa.Column("action_due_at", sa.DateTime(timezone=True)),
        sa.Column("action_completed_at", sa.DateTime(timezone=True)),
        sa.Column("action_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_plan_version", sa.Integer(), nullable=False, server_default="0")]:
        op.add_column("alerts", column, schema="alerts")
    op.add_column("alert_history", sa.Column("event_type", sa.String(40), nullable=False, server_default="STATUS_CHANGED"), schema="alerts")
    op.add_column("alert_history", sa.Column("details", JSONB()), schema="alerts")
    op.create_table("corrective_evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(100)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.String(100)), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("developer_remark", sa.Text()),
        sa.Column("enterprise_id", sa.BigInteger(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), sa.ForeignKey("alerts.alerts.id"), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False), sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False), sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False), schema="alerts")
    op.create_index("ix_alerts_corrective_evidence_public_id", "corrective_evidence", ["public_id"], unique=True, schema="alerts")
    op.create_index("ix_corrective_evidence_alert", "corrective_evidence", ["alert_id", "plan_version"], schema="alerts")


def downgrade():
    op.drop_table("corrective_evidence", schema="alerts")
    op.drop_column("alert_history", "details", schema="alerts")
    op.drop_column("alert_history", "event_type", schema="alerts")
    for column in ["action_description", "action_due_at", "action_completed_at", "action_revision", "action_plan_version"]:
        op.drop_column("alerts", column, schema="alerts")
