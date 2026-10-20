"""Track fresh inference evidence independently of camera activation status."""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("camera_applications", sa.Column("health_reported_at", sa.DateTime(timezone=True)), schema="config")
    op.add_column("camera_applications", sa.Column("last_inference_at", sa.DateTime(timezone=True)), schema="config")


def downgrade():
    op.drop_column("camera_applications", "last_inference_at", schema="config")
    op.drop_column("camera_applications", "health_reported_at", schema="config")
