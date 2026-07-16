"""Per-zone and per-camera mandatory PPE rules

Replaces config.zone_configs.ppe_required (a JSONB list) with five explicit
boolean columns — helmet_required, vest_required, gloves_required,
shoes_required, mask_required — so each item maps to a single checkbox in
the UI instead of a freeform list.

Also adds the same five columns to cameras, all nullable: NULL means "no
override, inherit the zone's setting", non-null means this specific camera
overrides its zone's default for that item. This is what lets two cameras
in the same zone enforce different PPE (e.g. a zone-wide helmet+vest
default, with one camera in a heavier-work area also requiring gloves).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_ITEM_DEFAULTS = {
    "helmet_required": "true",
    "vest_required": "true",
    "gloves_required": "false",
    "shoes_required": "false",
    "mask_required": "false",
}


def upgrade() -> None:
    for col, default in _ITEM_DEFAULTS.items():
        op.add_column(
            "zone_configs",
            sa.Column(col, sa.Boolean, nullable=False, server_default=default),
            schema="config",
        )

    # Backfill from the existing ppe_required JSONB list before dropping it —
    # `?` is the JSONB "does this array contain this element" operator.
    op.execute("""
        UPDATE config.zone_configs SET
            helmet_required = ppe_required ? 'helmet',
            vest_required   = ppe_required ? 'vest',
            gloves_required = ppe_required ? 'gloves',
            shoes_required  = ppe_required ? 'shoes',
            mask_required   = ppe_required ? 'mask'
        WHERE ppe_required IS NOT NULL
    """)

    op.drop_column("zone_configs", "ppe_required", schema="config")

    for col in _ITEM_DEFAULTS:
        op.add_column("cameras", sa.Column(col, sa.Boolean, nullable=True))


def downgrade() -> None:
    for col in _ITEM_DEFAULTS:
        op.drop_column("cameras", col)

    op.add_column(
        "zone_configs",
        sa.Column("ppe_required", JSONB, server_default='["helmet","vest"]'),
        schema="config",
    )
    op.execute("""
        UPDATE config.zone_configs SET ppe_required = (
            SELECT COALESCE(jsonb_agg(item), '[]'::jsonb) FROM (
                SELECT 'helmet' AS item WHERE helmet_required
                UNION ALL SELECT 'vest' WHERE vest_required
                UNION ALL SELECT 'gloves' WHERE gloves_required
                UNION ALL SELECT 'shoes' WHERE shoes_required
                UNION ALL SELECT 'mask' WHERE mask_required
            ) t
        )
    """)
    for col in _ITEM_DEFAULTS:
        op.drop_column("zone_configs", col, schema="config")
