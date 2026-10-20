"""Queue report generation with bounded, fenced background attempts."""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("request_key", sa.String(36)),
        sa.Column("stage", sa.String(30), nullable=False, server_default="Completed"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_token", sa.String(36)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(60)), sa.Column("row_count", sa.Integer()),
    ]:
        op.add_column("reports", column, schema="reports")
    op.create_index("ix_reports_due", "reports", ["status", "next_attempt_at"], schema="reports")
    op.create_unique_constraint("uq_report_request_key", "reports", ["enterprise_id", "request_key"], schema="reports")


def downgrade():
    op.drop_constraint("uq_report_request_key", "reports", schema="reports", type_="unique")
    op.drop_index("ix_reports_due", table_name="reports", schema="reports")
    for name in ["request_key", "stage", "attempts", "attempt_limit", "next_attempt_at", "lease_token",
                 "lease_expires_at", "started_at", "completed_at", "failure_code", "row_count"]:
        op.drop_column("reports", name, schema="reports")
