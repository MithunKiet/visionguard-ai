"""Require explicit factory scope and capacity before worker admission."""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_workers", sa.Column("factory_id", sa.BigInteger(), nullable=True), schema="worker")
    op.add_column("ai_workers", sa.Column("max_cameras", sa.Integer(), nullable=False, server_default="0"), schema="worker")
    op.create_foreign_key("fk_ai_workers_factory", "ai_workers", "factories", ["factory_id"], ["id"], source_schema="worker")
    op.create_index("ix_worker_ai_workers_factory_id", "ai_workers", ["factory_id"], schema="worker")
    op.create_check_constraint("ck_ai_workers_max_cameras", "ai_workers", "max_cameras >= 0", schema="worker")


def downgrade():
    op.drop_constraint("ck_ai_workers_max_cameras", "ai_workers", schema="worker", type_="check")
    op.drop_index("ix_worker_ai_workers_factory_id", table_name="ai_workers", schema="worker")
    op.drop_constraint("fk_ai_workers_factory", "ai_workers", schema="worker", type_="foreignkey")
    op.drop_column("ai_workers", "max_cameras", schema="worker")
    op.drop_column("ai_workers", "factory_id", schema="worker")
