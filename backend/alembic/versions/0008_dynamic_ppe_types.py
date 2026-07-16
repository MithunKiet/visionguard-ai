"""Dynamic PPE types

Replaces the fixed 5-column PPE model (helmet_required/vest_required/...)
with a proper catalog: enterprises can define their own PPE types at
runtime instead of being limited to a hardcoded set — a fixed set of named
columns can't express "add a 6th type" without a schema change, so this
moves to a JSONB list of type codes.

- ppe_types: enterprise-scoped catalog (code, display name, active flag).
  Seeded with the 5 previous defaults for every existing enterprise.
- config.zone_configs.required_ppe_types: JSONB list of codes, replacing
  the 5 boolean columns (backfilled from them).
- cameras.ppe_overrides: JSONB object {code: bool}, replacing the 5
  nullable boolean columns — only overridden codes are present; a camera
  with no entry for a code inherits its zone's setting for that code.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_DEFAULT_TYPES = [
    ("helmet", "Helmet"),
    ("vest", "Vest"),
    ("gloves", "Gloves"),
    ("shoes", "Shoes"),
    ("mask", "Mask"),
]


def upgrade() -> None:
    op.create_table(
        "ppe_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id", UUID(as_uuid=True),
                  sa.ForeignKey("enterprises.id"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_on", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("identity.users.id"), nullable=True),
        sa.UniqueConstraint("enterprise_id", "code", name="uq_ppe_types_enterprise_code"),
    )

    # Seed the previous fixed set for every existing enterprise so nothing
    # already relying on these 5 codes silently loses its catalog entry.
    for code, name in _DEFAULT_TYPES:
        op.execute(f"""
            INSERT INTO ppe_types (id, enterprise_id, code, name, is_active)
            SELECT gen_random_uuid(), id, '{code}', '{name}', true FROM enterprises
        """)

    op.add_column(
        "zone_configs",
        sa.Column("required_ppe_types", JSONB, server_default='["helmet","vest"]'),
        schema="config",
    )
    op.execute("""
        UPDATE config.zone_configs SET required_ppe_types = (
            SELECT COALESCE(jsonb_agg(item), '[]'::jsonb) FROM (
                SELECT 'helmet' AS item WHERE helmet_required
                UNION ALL SELECT 'vest' WHERE vest_required
                UNION ALL SELECT 'gloves' WHERE gloves_required
                UNION ALL SELECT 'shoes' WHERE shoes_required
                UNION ALL SELECT 'mask' WHERE mask_required
            ) t
        )
    """)
    for col in ("helmet_required", "vest_required", "gloves_required", "shoes_required", "mask_required"):
        op.drop_column("zone_configs", col, schema="config")

    op.add_column("cameras", sa.Column("ppe_overrides", JSONB, server_default="{}"))
    op.execute("""
        UPDATE cameras SET ppe_overrides = (
            SELECT COALESCE(jsonb_object_agg(item, val), '{}'::jsonb) FROM (
                SELECT 'helmet' AS item, helmet_required AS val WHERE helmet_required IS NOT NULL
                UNION ALL SELECT 'vest', vest_required WHERE vest_required IS NOT NULL
                UNION ALL SELECT 'gloves', gloves_required WHERE gloves_required IS NOT NULL
                UNION ALL SELECT 'shoes', shoes_required WHERE shoes_required IS NOT NULL
                UNION ALL SELECT 'mask', mask_required WHERE mask_required IS NOT NULL
            ) t
        )
    """)
    for col in ("helmet_required", "vest_required", "gloves_required", "shoes_required", "mask_required"):
        op.drop_column("cameras", col)


def downgrade() -> None:
    for col in ("helmet_required", "vest_required", "gloves_required", "shoes_required", "mask_required"):
        op.add_column("cameras", sa.Column(col, sa.Boolean, nullable=True))
    op.execute("""
        UPDATE cameras SET
            helmet_required = (ppe_overrides->>'helmet')::boolean,
            vest_required   = (ppe_overrides->>'vest')::boolean,
            gloves_required = (ppe_overrides->>'gloves')::boolean,
            shoes_required  = (ppe_overrides->>'shoes')::boolean,
            mask_required   = (ppe_overrides->>'mask')::boolean
    """)
    op.drop_column("cameras", "ppe_overrides")

    for col, default in (
        ("helmet_required", "true"), ("vest_required", "true"), ("gloves_required", "false"),
        ("shoes_required", "false"), ("mask_required", "false"),
    ):
        op.add_column("zone_configs", sa.Column(col, sa.Boolean, nullable=False, server_default=default),
                      schema="config")
    op.execute("""
        UPDATE config.zone_configs SET
            helmet_required = required_ppe_types ? 'helmet',
            vest_required   = required_ppe_types ? 'vest',
            gloves_required = required_ppe_types ? 'gloves',
            shoes_required  = required_ppe_types ? 'shoes',
            mask_required   = required_ppe_types ? 'mask'
    """)
    op.drop_column("zone_configs", "required_ppe_types", schema="config")

    op.drop_table("ppe_types")
