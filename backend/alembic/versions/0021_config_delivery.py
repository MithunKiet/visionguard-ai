"""Durable configuration publication and lease-bound application confirmations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("deliveries",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("enterprise_id", sa.BigInteger(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id", sa.BigInteger(), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(100)),
        sa.UniqueConstraint("zone_id", "version", name="uq_config_delivery_version"), schema="config")
    op.create_index("ix_config_deliveries_due", "deliveries", ["status", "next_attempt_at"], schema="config")
    op.create_table("camera_applications",
        sa.Column("camera_id", sa.BigInteger(), sa.ForeignKey("cameras.id"), primary_key=True),
        sa.Column("zone_id", sa.BigInteger(), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36), sa.ForeignKey("worker.camera_leases.token"), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False), schema="config")


def downgrade():
    op.drop_table("camera_applications", schema="config")
    op.drop_table("deliveries", schema="config")
