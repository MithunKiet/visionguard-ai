"""Per-asset fire extinguisher registry, reference fingerprints and incidents."""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _base_columns():
    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(100)), sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(100)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", sa.String(100)), sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("developer_remark", sa.Text()),
    ]


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS assets")
    op.create_table("safety_assets", *_base_columns(),
        sa.Column("enterprise_id", sa.BigInteger(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("factory_id", sa.BigInteger(), sa.ForeignKey("factories.id"), nullable=False),
        sa.Column("zone_id", sa.BigInteger(), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("camera_id", sa.BigInteger(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("asset_code", sa.String(50), nullable=False),
        sa.Column("asset_type", sa.String(50), nullable=False, server_default="FIRE_EXTINGUISHER"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location_desc", sa.String(300)),
        sa.Column("roi_x", sa.Float()), sa.Column("roi_y", sa.Float()),
        sa.Column("roi_width", sa.Float()), sa.Column("roi_height", sa.Float()),
        sa.Column("reference_key", sa.String(500)),
        sa.Column("reference_sha256", sa.String(64)),
        sa.Column("reference_width", sa.Integer()), sa.Column("reference_height", sa.Integer()),
        sa.Column("reference_captured_at", sa.DateTime(timezone=True)),
        sa.Column("roi_fingerprint", sa.Text()),
        sa.Column("scene_fingerprint", sa.Text()),
        sa.Column("check_interval_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("change_after_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("similarity_threshold", sa.Float(), nullable=False, server_default="0.6"),
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_state", sa.String(30)),
        sa.Column("last_similarity", sa.Float()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("check_interval_seconds BETWEEN 10 AND 3600", name="ck_safety_assets_interval"),
        sa.CheckConstraint("change_after_seconds BETWEEN 30 AND 86400", name="ck_safety_assets_change_after"),
        sa.CheckConstraint("similarity_threshold > 0 AND similarity_threshold < 1", name="ck_safety_assets_threshold"),
        schema="assets")
    op.create_index("ix_assets_safety_assets_public_id", "safety_assets", ["public_id"], unique=True, schema="assets")
    op.create_index("ix_safety_assets_camera", "safety_assets", ["camera_id"], schema="assets")
    op.create_index("ix_safety_assets_zone", "safety_assets", ["zone_id"], schema="assets")
    # Codes are unique per enterprise among live (not soft-deleted) assets.
    op.create_index("uq_safety_assets_code", "safety_assets", ["enterprise_id", "asset_code"], unique=True,
                    schema="assets", postgresql_where=sa.text("deleted_at IS NULL"))

    op.create_table("asset_incidents", *_base_columns(),
        sa.Column("enterprise_id", sa.BigInteger(), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.safety_assets.id"), nullable=False),
        sa.Column("camera_id", sa.BigInteger(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), sa.ForeignKey("alerts.alerts.id")),
        sa.Column("event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("similarity", sa.Float()),
        sa.Column("scene_similarity", sa.Float()),
        sa.Column("snapshot_key", sa.String(500)),
        sa.Column("config_version", sa.Integer()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True)),
        schema="assets")
    op.create_index("ix_assets_asset_incidents_public_id", "asset_incidents", ["public_id"], unique=True, schema="assets")
    op.create_index("ix_asset_incidents_asset", "asset_incidents", ["asset_id", "detected_at"], schema="assets")
    op.create_index("ix_asset_incidents_alert", "asset_incidents", ["alert_id"], schema="assets")


def downgrade():
    op.drop_table("asset_incidents", schema="assets")
    op.drop_table("safety_assets", schema="assets")
    op.execute("DROP SCHEMA IF EXISTS assets")
