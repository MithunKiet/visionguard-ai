"""Fence camera ownership and retain lease history for durable replay."""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cameras", sa.Column("assignment_generation", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_table("camera_leases",
        sa.Column("token", sa.String(36), primary_key=True),
        sa.Column("camera_id", sa.BigInteger(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("worker_id", sa.BigInteger(), sa.ForeignKey("worker.ai_workers.id"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("camera_id", "generation", name="uq_camera_lease_generation"),
        schema="worker")


def downgrade():
    op.drop_table("camera_leases", schema="worker")
    op.drop_column("cameras", "assignment_generation")
