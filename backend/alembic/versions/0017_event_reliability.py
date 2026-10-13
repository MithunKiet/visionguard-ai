"""Persist event receipts and review state; allocate alert numbers atomically."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE alerts.alert_number_seq")
    op.execute("SELECT setval('alerts.alert_number_seq', GREATEST(COALESCE((SELECT MAX(substring(alert_number FROM '[0-9]+$')::bigint) FROM alerts.alerts), 0) + 1, 1), false)")
    op.create_table(
        "event_receipts",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("violations", sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()), schema="ppe")
    op.add_column("violations", sa.Column("bbox", JSONB(), nullable=True), schema="ppe")
    op.execute("UPDATE ppe.violations SET needs_review = true WHERE confidence < 0.60")


def downgrade():
    op.drop_column("violations", "bbox", schema="ppe")
    op.drop_column("violations", "needs_review", schema="ppe")
    op.drop_table("event_receipts")
    op.execute("DROP SEQUENCE alerts.alert_number_seq")
