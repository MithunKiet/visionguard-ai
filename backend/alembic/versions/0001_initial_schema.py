"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create schemas ──────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.execute("CREATE SCHEMA IF NOT EXISTS worker")
    op.execute("CREATE SCHEMA IF NOT EXISTS config")
    op.execute("CREATE SCHEMA IF NOT EXISTS occupancy")
    op.execute("CREATE SCHEMA IF NOT EXISTS ppe")
    op.execute("CREATE SCHEMA IF NOT EXISTS alerts")
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("CREATE SCHEMA IF NOT EXISTS onboarding")

    # ── enterprises ─────────────────────────────────────────────────────────
    op.create_table(
        "enterprises",
        sa.Column("id",              UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name",            sa.String(200), nullable=False),
        sa.Column("code",            sa.String(50),  nullable=False, unique=True),
        sa.Column("logo_url",        sa.String(500)),
        sa.Column("favicon_url",     sa.String(500)),
        sa.Column("primary_color",   sa.String(7),   server_default="#1565C0"),
        sa.Column("secondary_color", sa.String(7),   server_default="#42A5F5"),
        sa.Column("tagline",         sa.String(300)),
        sa.Column("industry",        sa.String(100)),
        sa.Column("contact_person",  sa.String(200)),
        sa.Column("contact_email",   sa.String(200)),
        sa.Column("status",          sa.String(20),  nullable=False, server_default="Active"),
        sa.Column("created_on",      sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── identity.users ──────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",                  UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",       UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("name",                sa.String(200), nullable=False),
        sa.Column("email",               sa.String(200), nullable=False, unique=True),
        sa.Column("password_hash",       sa.String(500), nullable=False),
        sa.Column("role",                sa.String(50),  nullable=False),
        sa.Column("factory_id",          UUID(as_uuid=True), nullable=True),
        sa.Column("department_id",       UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_zone_ids",   JSONB, server_default="[]"),
        sa.Column("status",              sa.String(20), nullable=False, server_default="Active"),
        sa.Column("is_first_login",      sa.Boolean, nullable=False, server_default="true"),
        sa.Column("setup_completed",     sa.Boolean, nullable=False, server_default="false"),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
        sa.Column("totp_enabled",        sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dnd_enabled",         sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dnd_start",           sa.Time),
        sa.Column("dnd_end",             sa.Time),
        sa.Column("notification_prefs",  JSONB, server_default="{}"),
        sa.Column("session_timeout_min", sa.Integer),
        sa.Column("last_login_at",       sa.DateTime(timezone=True)),
        sa.Column("invited_by",          UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("invited_at",          sa.DateTime(timezone=True)),
        sa.Column("created_on",          sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("deleted_at",          sa.DateTime(timezone=True)),
        schema="identity",
    )
    op.create_index("ix_users_enterprise_id", "users", ["enterprise_id"], schema="identity")

    op.create_table(
        "refresh_tokens",
        sa.Column("id",         UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id",    UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("token_hash", sa.String(500), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked",    sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="identity",
    )

    # ── factories ───────────────────────────────────────────────────────────
    op.create_table(
        "factories",
        sa.Column("id",            UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("name",          sa.String(200), nullable=False),
        sa.Column("code",          sa.String(50),  nullable=False),
        sa.Column("location",      sa.String(300)),
        sa.Column("plant_head_id", UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("status",        sa.String(20), nullable=False, server_default="Active"),
        sa.Column("created_on",    sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("modified_on",   sa.DateTime(timezone=True)),
        sa.Column("deleted_at",    sa.DateTime(timezone=True)),
        sa.Column("version",       sa.Integer, server_default="1"),
    )
    op.create_index("ix_factories_enterprise_id", "factories", ["enterprise_id"])

    # Add FK from users → factories (after factories table exists)
    op.create_foreign_key("fk_users_factory",     "users", "factories",    ["factory_id"],    ["id"], source_schema="identity")

    # ── departments ─────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id",            UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("factory_id",    UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
        sa.Column("name",          sa.String(200), nullable=False),
        sa.Column("code",          sa.String(50),  nullable=False),
        sa.Column("head_user_id",  UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("status",        sa.String(20), nullable=False, server_default="Active"),
        sa.Column("created_on",    sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("modified_on",   sa.DateTime(timezone=True)),
        sa.Column("deleted_at",    sa.DateTime(timezone=True)),
        sa.Column("version",       sa.Integer, server_default="1"),
    )
    op.create_index("ix_departments_enterprise_id", "departments", ["enterprise_id"])
    op.create_index("ix_departments_factory_id",    "departments", ["factory_id"])

    # Add FK from users → departments (after departments table exists)
    op.create_foreign_key("fk_users_department",  "users", "departments",  ["department_id"], ["id"], source_schema="identity")

    # ── zones ───────────────────────────────────────────────────────────────
    op.create_table(
        "zones",
        sa.Column("id",            UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("factory_id",    UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("name",          sa.String(200), nullable=False),
        sa.Column("code",          sa.String(50),  nullable=False),
        sa.Column("max_occupancy", sa.Integer, nullable=False),
        sa.Column("supervisor_id", UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("zone_type",     sa.String(50), server_default="Production"),
        sa.Column("is_restricted", sa.Boolean, server_default="false"),
        sa.Column("status",        sa.String(20), nullable=False, server_default="Active"),
        sa.Column("created_on",    sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("modified_on",   sa.DateTime(timezone=True)),
        sa.Column("deleted_at",    sa.DateTime(timezone=True)),
        sa.Column("version",       sa.Integer, server_default="1"),
    )
    op.create_index("ix_zones_enterprise_id",  "zones", ["enterprise_id"])
    op.create_index("ix_zones_factory_id",     "zones", ["factory_id"])
    op.create_index("ix_zones_department_id",  "zones", ["department_id"])

    # ── worker.ai_workers ───────────────────────────────────────────────────
    op.create_table(
        "ai_workers",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",  UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("worker_id",      sa.String(100), nullable=False, unique=True),
        sa.Column("hostname",       sa.String(200)),
        sa.Column("status",         sa.String(20), server_default="Online"),
        sa.Column("model_version",  sa.String(50)),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True)),
        sa.Column("gpu_available",  sa.Boolean, server_default="false"),
        sa.Column("created_on",     sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="worker",
    )

    # ── cameras ─────────────────────────────────────────────────────────────
    op.create_table(
        "cameras",
        sa.Column("id",                UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",     UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("factory_id",        UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
        sa.Column("zone_id",           UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("worker_id",         UUID(as_uuid=True), sa.ForeignKey("worker.ai_workers.id")),
        sa.Column("name",              sa.String(200), nullable=False),
        sa.Column("code",              sa.String(50),  nullable=False),
        sa.Column("rtsp_url",          sa.String(500), nullable=False),
        sa.Column("camera_type",       sa.String(50),  server_default="Fixed"),
        sa.Column("position_desc",     sa.String(300)),
        sa.Column("status",            sa.String(20),  server_default="Active"),
        sa.Column("fps",               sa.Float),
        sa.Column("last_seen_at",      sa.DateTime(timezone=True)),
        sa.Column("in_maintenance",    sa.Boolean, server_default="false"),
        sa.Column("maintenance_until", sa.DateTime(timezone=True)),
        sa.Column("created_on",        sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("modified_on",       sa.DateTime(timezone=True)),
        sa.Column("deleted_at",        sa.DateTime(timezone=True)),
        sa.Column("version",           sa.Integer, server_default="1"),
    )
    op.create_index("ix_cameras_enterprise_id", "cameras", ["enterprise_id"])
    op.create_index("ix_cameras_zone_id",       "cameras", ["zone_id"])

    # ── shifts ──────────────────────────────────────────────────────────────
    op.create_table(
        "shifts",
        sa.Column("id",            UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("factory_id",    UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
        sa.Column("name",          sa.String(100), nullable=False),
        sa.Column("start_time",    sa.Time, nullable=False),
        sa.Column("end_time",      sa.Time, nullable=False),
        sa.Column("days",          JSONB, server_default='["MON","TUE","WED","THU","FRI"]'),
        sa.Column("status",        sa.String(20), server_default="Active"),
    )

    # ── config.zone_configs ─────────────────────────────────────────────────
    op.create_table(
        "zone_configs",
        sa.Column("id",                 UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",      UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id",            UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False, unique=True),
        sa.Column("person_threshold",   sa.Float, server_default="0.70"),
        sa.Column("helmet_threshold",   sa.Float, server_default="0.75"),
        sa.Column("vest_threshold",     sa.Float, server_default="0.75"),
        sa.Column("gloves_threshold",   sa.Float, server_default="0.70"),
        sa.Column("shoes_threshold",    sa.Float, server_default="0.70"),
        sa.Column("mask_threshold",     sa.Float, server_default="0.75"),
        sa.Column("max_occupancy",      sa.Integer),
        sa.Column("frame_sample_fps",   sa.Integer, server_default="2"),
        sa.Column("ppe_required",       JSONB, server_default='["helmet","vest"]'),
        sa.Column("cooldown_seconds",   sa.Integer, server_default="120"),
        sa.Column("updated_by",         UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("updated_at",         sa.DateTime(timezone=True)),
        sa.Column("version",            sa.Integer, nullable=False, server_default="1"),
        schema="config",
    )

    op.create_table(
        "zone_rules",
        sa.Column("id",                UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",     UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id",           UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("rule_name",         sa.String(200), nullable=False),
        sa.Column("condition_type",    sa.String(100), nullable=False),
        sa.Column("duration_seconds",  sa.Integer, server_default="3"),
        sa.Column("cooldown_seconds",  sa.Integer, server_default="120"),
        sa.Column("severity",          sa.String(20), server_default="High"),
        sa.Column("enabled",           sa.Boolean, server_default="true"),
        sa.Column("actions",           JSONB, server_default='["CREATE_ALERT","STORE_SNAPSHOT"]'),
        sa.Column("notify_roles",      JSONB, server_default='["Supervisor"]'),
        sa.Column("notify_channels",   JSONB, server_default='["Email","InApp"]'),
        sa.Column("created_by",        UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("created_on",        sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="config",
    )

    # ── occupancy.logs ──────────────────────────────────────────────────────
    op.create_table(
        "logs",
        sa.Column("id",            UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id", UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id",       UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("camera_id",     UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("current_count", sa.Integer, nullable=False),
        sa.Column("shift_id",      UUID(as_uuid=True), sa.ForeignKey("shifts.id")),
        sa.Column("timestamp",     sa.DateTime(timezone=True), nullable=False),
        schema="occupancy",
    )
    op.create_index("ix_occupancy_zone_ts", "logs", ["zone_id", "timestamp"], schema="occupancy")

    # ── ppe.violations ──────────────────────────────────────────────────────
    op.create_table(
        "violations",
        sa.Column("id",                UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",     UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("zone_id",           UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("camera_id",         UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("violation_type",    sa.String(50), nullable=False),
        sa.Column("confidence",        sa.Float, nullable=False),
        sa.Column("snapshot_key",      sa.String(500)),
        sa.Column("track_id",          sa.String(100)),
        sa.Column("shift_id",          UUID(as_uuid=True), sa.ForeignKey("shifts.id")),
        sa.Column("rule_id",           UUID(as_uuid=True), sa.ForeignKey("config.zone_rules.id")),
        sa.Column("is_false_positive", sa.Boolean, server_default="false"),
        sa.Column("fp_reason",         sa.String(200)),
        sa.Column("created_on",        sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        schema="ppe",
    )
    op.create_index("ix_violation_zone_ts", "violations", ["zone_id", "created_on"], schema="ppe")

    # ── alerts.alerts ───────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id",              UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",   UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("factory_id",      UUID(as_uuid=True), sa.ForeignKey("factories.id"), nullable=False),
        sa.Column("department_id",   UUID(as_uuid=True), sa.ForeignKey("departments.id")),
        sa.Column("zone_id",         UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("camera_id",       UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("violation_id",    UUID(as_uuid=True), sa.ForeignKey("ppe.violations.id")),
        sa.Column("alert_number",    sa.String(30), nullable=False, unique=True),
        sa.Column("alert_type",      sa.String(100), nullable=False),
        sa.Column("severity",        sa.String(20), nullable=False),
        sa.Column("status",          sa.String(30), nullable=False, server_default="Open"),
        sa.Column("assigned_to",     UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("shift_id",        UUID(as_uuid=True), sa.ForeignKey("shifts.id")),
        sa.Column("sla_due_at",      sa.DateTime(timezone=True)),
        sa.Column("created_on",      sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("acknowledged_on", sa.DateTime(timezone=True)),
        sa.Column("resolved_on",     sa.DateTime(timezone=True)),
        sa.Column("created_by",      sa.String(100), server_default="system"),
        schema="alerts",
    )
    op.create_index("ix_alert_enterprise_status", "alerts", ["enterprise_id", "status"], schema="alerts")

    op.create_table(
        "alert_history",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_id",    UUID(as_uuid=True), sa.ForeignKey("alerts.alerts.id"), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status",   sa.String(30)),
        sa.Column("changed_by",  UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("changed_at",  sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("comment",     sa.Text),
        schema="alerts",
    )

    # ── notifications.notification_log ──────────────────────────────────────
    op.create_table(
        "notification_log",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",  UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("alert_id",       UUID(as_uuid=True), sa.ForeignKey("alerts.alerts.id")),
        sa.Column("channel",        sa.String(30), nullable=False),
        sa.Column("recipient_id",   UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("sent_at",        sa.DateTime(timezone=True)),
        sa.Column("status",         sa.String(20), server_default="Sent"),
        sa.Column("failure_reason", sa.Text),
        sa.Column("retry_count",    sa.Integer, server_default="0"),
        schema="notifications",
    )

    # ── audit.audit_log ─────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",  UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("user_id",        UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("action",         sa.String(100), nullable=False),
        sa.Column("entity_type",    sa.String(100)),
        sa.Column("entity_id",      UUID(as_uuid=True)),
        sa.Column("old_value",      JSONB),
        sa.Column("new_value",      JSONB),
        sa.Column("ip_address",     sa.String(50)),
        sa.Column("user_agent",     sa.Text),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("timestamp",      sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        schema="audit",
    )
    op.create_index("ix_audit_enterprise_ts", "audit_log", ["enterprise_id", "timestamp"], schema="audit")

    # ── camera_maintenance ──────────────────────────────────────────────────
    op.create_table(
        "camera_maintenance",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("enterprise_id",    UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("camera_id",        UUID(as_uuid=True), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("scheduled_date",   sa.Date),
        sa.Column("maintenance_type", sa.String(50)),
        sa.Column("assigned_to",      UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("status",           sa.String(30), server_default="Scheduled"),
        sa.Column("notes",            sa.Text),
        sa.Column("completed_at",     sa.DateTime(timezone=True)),
        sa.Column("completed_by",     UUID(as_uuid=True), sa.ForeignKey("identity.users.id")),
        sa.Column("completion_notes", sa.Text),
        sa.Column("next_due_date",    sa.Date),
    )

    # ── onboarding.setup_progress ───────────────────────────────────────────
    op.create_table(
        "setup_progress",
        sa.Column("id",                  UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id",             UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("enterprise_id",       UUID(as_uuid=True), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("last_completed_step", sa.Integer, server_default="0"),
        sa.Column("factory_id",          UUID(as_uuid=True), sa.ForeignKey("factories.id")),
        sa.Column("department_id",       UUID(as_uuid=True), sa.ForeignKey("departments.id")),
        sa.Column("zone_id",             UUID(as_uuid=True), sa.ForeignKey("zones.id")),
        sa.Column("camera_id",           UUID(as_uuid=True), sa.ForeignKey("cameras.id")),
        sa.Column("completed_at",        sa.DateTime(timezone=True)),
        schema="onboarding",
    )

    # ── Row-Level Security on audit_log (immutable) ─────────────────────────
    op.execute("ALTER TABLE audit.audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY audit_insert_only ON audit.audit_log
        FOR INSERT WITH CHECK (true)
    """)


def downgrade() -> None:
    op.drop_table("setup_progress",      schema="onboarding")
    op.drop_table("camera_maintenance")
    op.drop_table("audit_log",           schema="audit")
    op.drop_table("notification_log",    schema="notifications")
    op.drop_table("alert_history",       schema="alerts")
    op.drop_table("alerts",              schema="alerts")
    op.drop_table("violations",          schema="ppe")
    op.drop_table("logs",                schema="occupancy")
    op.drop_table("zone_rules",          schema="config")
    op.drop_table("zone_configs",        schema="config")
    op.drop_table("shifts")
    op.drop_table("cameras")
    op.drop_table("ai_workers",          schema="worker")
    op.drop_table("zones")
    op.drop_table("departments")
    op.drop_table("factories")
    op.drop_table("refresh_tokens",      schema="identity")
    op.drop_table("users",               schema="identity")
    op.drop_table("enterprises")

    op.execute("DROP SCHEMA IF EXISTS onboarding CASCADE")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS notifications CASCADE")
    op.execute("DROP SCHEMA IF EXISTS alerts CASCADE")
    op.execute("DROP SCHEMA IF EXISTS ppe CASCADE")
    op.execute("DROP SCHEMA IF EXISTS occupancy CASCADE")
    op.execute("DROP SCHEMA IF EXISTS config CASCADE")
    op.execute("DROP SCHEMA IF EXISTS worker CASCADE")
    op.execute("DROP SCHEMA IF EXISTS identity CASCADE")
