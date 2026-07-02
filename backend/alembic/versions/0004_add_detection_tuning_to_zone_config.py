"""Add required_consecutive_frames and low_confidence_floor to config.zone_configs

Moves two AI Worker detection-tuning constants (previously hardcoded via
env vars: REQUIRED_CONSECUTIVE_FRAMES, LOW_CONFIDENCE_FLOOR) into the
per-zone config row so they can be changed directly in the database
without redeploying the worker (picked up on its next restart/config fetch,
same as the existing frame_sample_fps/cooldown_seconds/*_threshold columns).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "zone_configs",
        sa.Column("required_consecutive_frames", sa.Integer, server_default="3"),
        schema="config",
    )
    op.add_column(
        "zone_configs",
        sa.Column("low_confidence_floor", sa.Float, server_default="0.40"),
        schema="config",
    )


def downgrade() -> None:
    op.drop_column("zone_configs", "low_confidence_floor", schema="config")
    op.drop_column("zone_configs", "required_consecutive_frames", schema="config")
