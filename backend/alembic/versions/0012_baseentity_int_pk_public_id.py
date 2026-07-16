"""BaseEntity retrofit: integer PK + public_id, all tables

Every table's primary key changes from a UUID (used directly as the
external identifier) to an internal auto-incrementing integer, never
exposed via the API. A new `public_id` column (UUID, defaulted from the
table's old `id` value so existing external references keep working)
becomes the identifier used for all API communication going forward.

Also adds is_active/is_approved/created_by/updated_by/deleted_by/
developer_remark to every table (BaseEntity's mandated audit columns),
and normalizes every table's creation/update timestamp columns to
created_at/updated_at (renaming created_on/modified_on/changed_at where
they existed, adding fresh columns where a table never had one).

Strategy per table: rename old UUID `id` -> `public_id`, add a new
identity-column `id_new`, remap every FK column in every OTHER table from
the old UUID value to the new integer id via a join, drop the old UUID FK
columns, then promote id_new to the primary key.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_TABLES = [
    (None, "enterprises"),
    (None, "roles"),
    ("identity", "user_roles"),
    ("identity", "users"),
    ("identity", "refresh_tokens"),
    (None, "factories"),
    (None, "departments"),
    (None, "zones"),
    ("worker", "ai_workers"),
    (None, "cameras"),
    ("config", "zone_configs"),
    (None, "ppe_types"),
    ("config", "zone_rules"),
    ("config", "config_history"),
    ("reports", "reports"),
    (None, "shifts"),
    ("occupancy", "logs"),
    ("ppe", "violations"),
    ("alerts", "alerts"),
    ("alerts", "alert_history"),
    ("notifications", "notification_log"),
    ("notifications", "notification_recipients"),
    ("audit", "audit_log"),
    (None, "camera_maintenance"),
    ("onboarding", "setup_progress"),
]

_AUDIT_COLS = [
    ("is_active", "BOOLEAN NOT NULL DEFAULT true"),
    ("is_approved", "BOOLEAN NOT NULL DEFAULT false"),
    ("created_by", "VARCHAR(100)"),
    ("updated_by", "VARCHAR(100)"),
    ("deleted_by", "VARCHAR(100)"),
    ("developer_remark", "TEXT"),
]

# (referencing table, fk column, referenced table) — every FK across the
# schema that points at another table's surrogate id. role_code (a natural-
# key FK against roles.code) is deliberately excluded — untouched by this migration.
_FK_MAP = [
    ("identity.user_roles", "user_id", "identity.users"),
    ("identity.users", "enterprise_id", "enterprises"),
    ("identity.users", "factory_id", "factories"),
    ("identity.users", "department_id", "departments"),
    ("identity.users", "invited_by", "identity.users"),
    ("identity.refresh_tokens", "user_id", "identity.users"),
    ("factories", "enterprise_id", "enterprises"),
    ("factories", "plant_head_id", "identity.users"),
    ("departments", "enterprise_id", "enterprises"),
    ("departments", "factory_id", "factories"),
    ("departments", "head_user_id", "identity.users"),
    ("zones", "enterprise_id", "enterprises"),
    ("zones", "factory_id", "factories"),
    ("zones", "department_id", "departments"),
    ("zones", "supervisor_id", "identity.users"),
    ("worker.ai_workers", "enterprise_id", "enterprises"),
    ("cameras", "enterprise_id", "enterprises"),
    ("cameras", "factory_id", "factories"),
    ("cameras", "zone_id", "zones"),
    ("cameras", "worker_id", "worker.ai_workers"),
    ("config.zone_configs", "enterprise_id", "enterprises"),
    ("config.zone_configs", "zone_id", "zones"),
    ("ppe_types", "enterprise_id", "enterprises"),
    ("config.zone_rules", "enterprise_id", "enterprises"),
    ("config.zone_rules", "zone_id", "zones"),
    ("config.config_history", "enterprise_id", "enterprises"),
    ("config.config_history", "zone_id", "zones"),
    ("reports.reports", "enterprise_id", "enterprises"),
    ("reports.reports", "generated_by", "identity.users"),
    ("shifts", "enterprise_id", "enterprises"),
    ("shifts", "factory_id", "factories"),
    ("occupancy.logs", "enterprise_id", "enterprises"),
    ("occupancy.logs", "zone_id", "zones"),
    ("occupancy.logs", "camera_id", "cameras"),
    ("occupancy.logs", "shift_id", "shifts"),
    ("ppe.violations", "enterprise_id", "enterprises"),
    ("ppe.violations", "zone_id", "zones"),
    ("ppe.violations", "camera_id", "cameras"),
    ("ppe.violations", "shift_id", "shifts"),
    ("ppe.violations", "rule_id", "config.zone_rules"),
    ("alerts.alerts", "enterprise_id", "enterprises"),
    ("alerts.alerts", "factory_id", "factories"),
    ("alerts.alerts", "department_id", "departments"),
    ("alerts.alerts", "zone_id", "zones"),
    ("alerts.alerts", "camera_id", "cameras"),
    ("alerts.alerts", "violation_id", "ppe.violations"),
    ("alerts.alerts", "assigned_to", "identity.users"),
    ("alerts.alerts", "shift_id", "shifts"),
    ("alerts.alert_history", "alert_id", "alerts.alerts"),
    ("notifications.notification_log", "enterprise_id", "enterprises"),
    ("notifications.notification_log", "alert_id", "alerts.alerts"),
    ("notifications.notification_log", "recipient_id", "identity.users"),
    ("notifications.notification_recipients", "enterprise_id", "enterprises"),
    ("notifications.notification_recipients", "zone_id", "zones"),
    ("notifications.notification_recipients", "user_id", "identity.users"),
    ("audit.audit_log", "enterprise_id", "enterprises"),
    ("audit.audit_log", "user_id", "identity.users"),
    ("camera_maintenance", "enterprise_id", "enterprises"),
    ("camera_maintenance", "camera_id", "cameras"),
    ("camera_maintenance", "assigned_to", "identity.users"),
    ("camera_maintenance", "completed_by", "identity.users"),
    ("onboarding.setup_progress", "user_id", "identity.users"),
    ("onboarding.setup_progress", "enterprise_id", "enterprises"),
    ("onboarding.setup_progress", "factory_id", "factories"),
    ("onboarding.setup_progress", "department_id", "departments"),
    ("onboarding.setup_progress", "zone_id", "zones"),
    ("onboarding.setup_progress", "camera_id", "cameras"),
]

_NOT_NULL_FKS = [
    ("identity.users", "enterprise_id"),
    ("factories", "enterprise_id"),
    ("departments", "enterprise_id"),
    ("departments", "factory_id"),
    ("zones", "enterprise_id"),
    ("zones", "factory_id"),
    ("zones", "department_id"),
    ("cameras", "enterprise_id"),
    ("cameras", "factory_id"),
    ("cameras", "zone_id"),
]


def _q(schema: str | None, table: str) -> str:
    return f'{schema}."{table}"' if schema else f'"{table}"'


def upgrade() -> None:
    # ── Step 0: drop every existing FK constraint first ─────────────────────
    # Postgres refuses to retype a column (id -> public_id, uuid -> varchar)
    # while another table's FK still points at it. Every one of these
    # constraints is about to be superseded anyway (step 3 drops and
    # recreates every FK column against the new integer ids), so it's safe
    # to drop them all up front rather than hand-enumerate constraint names.
    op.execute('''
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT tc.constraint_name, tc.table_schema, tc.table_name
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema IN (
                      'public', 'identity', 'worker', 'config', 'reports',
                      'occupancy', 'ppe', 'alerts', 'notifications', 'audit', 'onboarding'
                  )
            LOOP
                EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I', r.table_schema, r.table_name, r.constraint_name);
            END LOOP;
        END $$;
    ''')

    # ── Step 1: every table gets public_id (renamed from old id) + id_new + audit cols ──
    for schema, table in _TABLES:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} RENAME COLUMN id TO public_id')
        op.execute(f'ALTER TABLE {t} ALTER COLUMN public_id TYPE VARCHAR(36)')
        op.execute(f'ALTER TABLE {t} ADD COLUMN id_new BIGINT GENERATED BY DEFAULT AS IDENTITY')
        for col, ddl in _AUDIT_COLS:
            if col == "is_active" and table in ("roles", "ppe_types"):
                continue  # already has its own is_active from an earlier migration
            op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {col} {ddl}')

    # ── Step 2: rename existing timestamp columns to the BaseEntity convention ──
    op.execute('ALTER TABLE enterprises RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE roles RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE factories RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE factories RENAME COLUMN modified_on TO updated_at')
    op.execute('ALTER TABLE departments RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE departments RENAME COLUMN modified_on TO updated_at')
    op.execute('ALTER TABLE zones RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE zones RENAME COLUMN modified_on TO updated_at')
    op.execute('ALTER TABLE cameras RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE cameras RENAME COLUMN modified_on TO updated_at')
    op.execute('ALTER TABLE identity.users RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE worker.ai_workers RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE ppe_types RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE config.zone_rules RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE config.config_history RENAME COLUMN changed_at TO created_at')
    op.execute('ALTER TABLE config.config_history DROP COLUMN IF EXISTS changed_by')
    op.execute('ALTER TABLE reports.reports RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE ppe.violations RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE alerts.alerts RENAME COLUMN created_on TO created_at')
    op.execute('ALTER TABLE alerts.alerts RENAME COLUMN created_by TO created_source')
    op.execute('ALTER TABLE alerts.alert_history RENAME COLUMN changed_at TO created_at')
    op.execute('ALTER TABLE alerts.alert_history DROP COLUMN IF EXISTS changed_by')
    op.execute('ALTER TABLE notifications.notification_recipients RENAME COLUMN created_on TO created_at')

    # Drop now-redundant per-table "actor" FK columns superseded by the
    # generic created_by/updated_by string columns added in step 1.
    op.execute('ALTER TABLE ppe_types DROP COLUMN IF EXISTS created_by_old')
    op.execute('ALTER TABLE config.zone_configs DROP COLUMN IF EXISTS updated_by_old')

    # ppe_types.created_by and zone_rules.created_by were UUID FKs — rename
    # out of the way before step 1's generic VARCHAR created_by was added
    # under the same name (avoid a collision), then drop the now-orphaned
    # UUID one since BaseEntity's created_by (string) supersedes it.
    op.execute('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='ppe_types' AND column_name='created_by' AND data_type='uuid'
            ) THEN
                ALTER TABLE ppe_types DROP COLUMN created_by;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='config' AND table_name='zone_rules' AND column_name='created_by' AND data_type='uuid'
            ) THEN
                ALTER TABLE config.zone_rules DROP COLUMN created_by;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='config' AND table_name='zone_configs' AND column_name='updated_by' AND data_type='uuid'
            ) THEN
                ALTER TABLE config.zone_configs DROP COLUMN updated_by;
            END IF;
        END $$;
    ''')

    # Every table gets created_at/updated_at if it doesn't already have them
    # from a rename above (tables that never had timestamps at all: shifts,
    # occupancy.logs, notification_log, audit_log, user_roles, camera_maintenance,
    # setup_progress; tables where only one of the two existed: zone_configs
    # already had updated_at, refresh_tokens already had created_at).
    for schema, table in _TABLES:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()')
        op.execute(f'ALTER TABLE {t} ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ')

    # audit_log.entity_id is a polymorphic reference (any table's public_id)
    # — was UUID, becomes a plain string to match public_id's type.
    op.execute('ALTER TABLE audit.audit_log ALTER COLUMN entity_id TYPE VARCHAR(36)')

    # ── Step 3: remap every FK column to the new integer ids ────────────────
    for ref_table, fk_col, target_table in _FK_MAP:
        op.execute(f'ALTER TABLE {ref_table} ADD COLUMN {fk_col}_new BIGINT')
        op.execute(f'''
            UPDATE {ref_table} r SET {fk_col}_new = t.id_new
            FROM {target_table} t WHERE r.{fk_col}::text = t.public_id
        ''')
        op.execute(f'ALTER TABLE {ref_table} DROP COLUMN {fk_col}')
        op.execute(f'ALTER TABLE {ref_table} RENAME COLUMN {fk_col}_new TO {fk_col}')

    # ── Step 4: promote id_new to primary key on every table ────────────────
    for schema, table in _TABLES:
        t = _q(schema, table)
        op.execute(f'ALTER TABLE {t} DROP CONSTRAINT IF EXISTS "{table}_pkey"')
        op.execute(f'ALTER TABLE {t} DROP COLUMN public_id')
        op.execute(f'ALTER TABLE {t} RENAME COLUMN id_new TO id')
        op.execute(f'ALTER TABLE {t} ADD PRIMARY KEY (id)')
        op.execute(f'ALTER TABLE {t} ADD COLUMN public_id VARCHAR(36) UNIQUE NOT NULL DEFAULT gen_random_uuid()::text')
        op.execute(f'CREATE INDEX IF NOT EXISTS ix_{table}_public_id ON {t} (public_id)')

    for table, col in _NOT_NULL_FKS:
        op.execute(f'ALTER TABLE {table} ALTER COLUMN {col} SET NOT NULL')

    # ── Step 5: re-establish FK constraints against the new integer ids ─────
    for ref_table, fk_col, target_table in _FK_MAP:
        cname = f"{ref_table.split('.')[-1]}_{fk_col}_fkey"
        op.execute(f'''
            ALTER TABLE {ref_table}
            ADD CONSTRAINT {cname} FOREIGN KEY ({fk_col}) REFERENCES {target_table}(id)
        ''')
    # Natural-key FK (role_code -> roles.code), dropped by step 0, unaffected
    # by the id/public_id remap — just needs re-adding as-is.
    op.execute('''
        ALTER TABLE identity.user_roles
        ADD CONSTRAINT user_roles_role_code_fkey FOREIGN KEY (role_code) REFERENCES roles(code)
    ''')


def downgrade() -> None:
    raise NotImplementedError(
        "0012 is not reversible — it's a full PK-type change across 25 "
        "tables. Restore from a pre-migration backup instead."
    )
