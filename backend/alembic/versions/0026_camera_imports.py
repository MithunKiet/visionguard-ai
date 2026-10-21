"""Durable camera import replay receipts without storing CSV credentials."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("camera_imports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(100)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.String(100)), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("developer_remark", sa.Text()),
        sa.Column("enterprise_id", sa.BigInteger(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False), sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("result", JSONB(), nullable=False),
        sa.UniqueConstraint("enterprise_id", "request_key", name="uq_camera_import_request"))
    op.create_index("ix_camera_imports_public_id", "camera_imports", ["public_id"], unique=True)


def downgrade():
    op.drop_table("camera_imports")
