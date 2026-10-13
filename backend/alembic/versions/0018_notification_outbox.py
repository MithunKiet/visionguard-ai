"""Commit notification delivery jobs atomically with alerts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(100)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.String(100)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("developer_remark", sa.Text()),
        sa.Column("enterprise_id", sa.BigInteger(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), sa.ForeignKey("alerts.alerts.id"), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), sa.ForeignKey("identity.users.id")),
        sa.Column("delivery_key", sa.String(160), nullable=False, unique=True),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(200)),
        schema="notifications",
    )
    op.create_index("ix_notifications_deliveries_public_id", "deliveries", ["public_id"], unique=True, schema="notifications")
    op.create_index("ix_deliveries_due", "deliveries", ["status", "next_attempt_at"], schema="notifications")
    op.create_index("ix_deliveries_enterprise_created", "deliveries", ["enterprise_id", "created_at"], schema="notifications")


def downgrade():
    op.drop_table("deliveries", schema="notifications")
