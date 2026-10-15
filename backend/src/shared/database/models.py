"""
All SQLAlchemy ORM models — single source of truth for Alembic migrations.
Every table follows the DB schema in AI_MASTER_CONTEXT.md Section 6.

Every model inherits BaseEntity (src/shared/database/base.py): internal
integer `id` (never exposed via API), `public_id` (UUID, used for all
external API communication), plus is_active/is_approved/created_by/
created_at/updated_by/updated_at/deleted_by/deleted_at/developer_remark.
Every foreign key below points at another model's internal integer `id`.
"""
from sqlalchemy import (
    Column, String, Boolean, BigInteger, Integer, Float, Text, Date,
    DateTime, Time, ForeignKey, Index, CheckConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.shared.database.base import Base, BaseEntity


# ─── Enterprises ─────────────────────────────────────────────────────────────

class Enterprise(BaseEntity):
    __tablename__ = "enterprises"

    name            = Column(String(200), nullable=False)
    code            = Column(String(50), unique=True, nullable=False)
    logo_url        = Column(String(500))
    favicon_url     = Column(String(500))
    primary_color   = Column(String(7), default="#1565C0")
    secondary_color = Column(String(7), default="#42A5F5")
    tagline         = Column(String(300))
    industry        = Column(String(100))
    contact_person  = Column(String(200))
    contact_email   = Column(String(200))
    status          = Column(String(20), default="Active", nullable=False)


# ─── Roles ────────────────────────────────────────────────────────────────────

class Role(BaseEntity):
    """Platform-wide catalog of valid role codes — not enterprise-scoped,
    since every enterprise shares the same role vocabulary and the
    authorization gates (require_roles() in each route module) hardcode
    these exact string values. users.roles entries should always match a
    code here; adding a row doesn't itself grant permissions — that's
    still wired per-endpoint in code."""
    __tablename__ = "roles"

    code            = Column(String(50), unique=True, nullable=False)
    name            = Column(String(100), nullable=False)
    description     = Column(String(300))
    scope           = Column(String(20), nullable=False)  # PLATFORM/ENTERPRISE/FACTORY/ZONE/ASSIGNED


class UserRole(Base):
    """Many-to-many: a user can hold more than one role at once (e.g.
    FACTORY_MANAGER + SAFETY_OFFICER) — authorization checks for
    intersection, not equality. A pure link table — not a BaseEntity: it
    carries no surrogate id/audit columns of its own, just the two parent
    tables' public_ids as a composite primary key."""
    __tablename__ = "user_roles"
    __table_args__ = {"schema": "identity"}

    user_public_id  = Column(String(36), ForeignKey("identity.users.public_id", ondelete="CASCADE"), primary_key=True)
    role_public_id  = Column(String(36), ForeignKey("roles.public_id", ondelete="RESTRICT"), primary_key=True)
    assigned_on     = Column(DateTime(timezone=True), server_default=func.now())


# ─── Identity ─────────────────────────────────────────────────────────────────

class User(BaseEntity):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=False, index=True)
    name                = Column(String(200), nullable=False)
    email               = Column(String(200), unique=True, nullable=False)
    password_hash       = Column(String(500), nullable=False)
    factory_id          = Column(BigInteger, ForeignKey("factories.id"), nullable=True)
    department_id       = Column(BigInteger, ForeignKey("departments.id"), nullable=True)
    assigned_zone_ids   = Column(JSONB, default=list)
    status              = Column(String(20), default="Active", nullable=False)
    is_first_login      = Column(Boolean, default=True, nullable=False)
    setup_completed     = Column(Boolean, default=False, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    totp_enabled        = Column(Boolean, default=False, nullable=False)
    dnd_enabled         = Column(Boolean, default=False, nullable=False)
    dnd_start           = Column(Time, nullable=True)
    dnd_end             = Column(Time, nullable=True)
    notification_prefs  = Column(JSONB, default=dict)
    session_timeout_min = Column(Integer, nullable=True)
    last_login_at       = Column(DateTime(timezone=True), nullable=True)
    invited_by          = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    invited_at          = Column(DateTime(timezone=True), nullable=True)


class RefreshToken(BaseEntity):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "identity"}

    user_id     = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True, index=True)
    token_hash  = Column(String(500), nullable=False, unique=True)
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    revoked     = Column(Boolean, default=False, nullable=False)


# ─── Factories ───────────────────────────────────────────────────────────────

class Factory(BaseEntity):
    __tablename__ = "factories"

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    code            = Column(String(50), nullable=False)
    location        = Column(String(300))
    plant_head_id   = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    status          = Column(String(20), default="Active", nullable=False)
    version         = Column(Integer, default=1)


class Department(BaseEntity):
    __tablename__ = "departments"

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id      = Column(BigInteger, ForeignKey("factories.id"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    code            = Column(String(50), nullable=False)
    head_user_id    = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    status          = Column(String(20), default="Active", nullable=False)
    version         = Column(Integer, default=1)


class Zone(BaseEntity):
    __tablename__ = "zones"

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id      = Column(BigInteger, ForeignKey("factories.id"), nullable=False, index=True)
    department_id   = Column(BigInteger, ForeignKey("departments.id"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    code            = Column(String(50), nullable=False)
    max_occupancy   = Column(Integer, nullable=False)
    supervisor_id   = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    zone_type       = Column(String(50), default="Production")
    is_restricted   = Column(Boolean, default=False)
    status          = Column(String(20), default="Active", nullable=False)
    version         = Column(Integer, default=1)


# ─── Workers ─────────────────────────────────────────────────────────────────

class AIWorker(BaseEntity):
    __tablename__ = "ai_workers"
    __table_args__ = (
        CheckConstraint("max_cameras >= 0", name="ck_ai_workers_max_cameras"),
        {"schema": "worker"},
    )

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    worker_id       = Column(String(100), unique=True, nullable=False)
    hostname        = Column(String(200))
    status          = Column(String(20), default="Online")
    model_version   = Column(String(50))
    last_heartbeat  = Column(DateTime(timezone=True))
    gpu_available   = Column(Boolean, default=False)
    factory_id      = Column(BigInteger, ForeignKey("factories.id"), nullable=True, index=True)
    max_cameras     = Column(Integer, nullable=False, default=0, server_default="0")


# ─── Cameras ─────────────────────────────────────────────────────────────────

class Camera(BaseEntity):
    __tablename__ = "cameras"

    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id          = Column(BigInteger, ForeignKey("factories.id"), nullable=False, index=True)
    zone_id             = Column(BigInteger, ForeignKey("zones.id"), nullable=False, index=True)
    worker_id           = Column(BigInteger, ForeignKey("worker.ai_workers.id"), nullable=True)
    name                = Column(String(200), nullable=False)
    code                = Column(String(50), nullable=False)
    rtsp_url            = Column(String(500), nullable=False)
    camera_type         = Column(String(50), default="Fixed")
    position_desc       = Column(String(300))
    status              = Column(String(20), default="Active")
    fps                 = Column(Float)
    last_seen_at        = Column(DateTime(timezone=True))
    in_maintenance      = Column(Boolean, default=False)
    maintenance_until   = Column(DateTime(timezone=True), nullable=True)
    # Per-camera PPE overrides keyed by ppe_types.code, e.g. {"gloves": true,
    # "vest": false}. A code absent here inherits its zone's setting.
    ppe_overrides       = Column(JSONB, default=dict)
    version             = Column(Integer, default=1)


# ─── Config ───────────────────────────────────────────────────────────────────

class ZoneConfig(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "zone_configs"
    __table_args__ = {"schema": "config"}

    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    zone_id             = Column(BigInteger, ForeignKey("zones.id"), unique=True, nullable=True)
    person_threshold    = Column(Float, default=0.70)
    helmet_threshold    = Column(Float, default=0.75)
    vest_threshold      = Column(Float, default=0.75)
    gloves_threshold    = Column(Float, default=0.70)
    shoes_threshold     = Column(Float, default=0.70)
    mask_threshold      = Column(Float, default=0.75)
    max_occupancy       = Column(Integer)
    frame_sample_fps    = Column(Integer, default=2)
    # List of ppe_types.code this zone requires by default, e.g. ["helmet","vest"].
    required_ppe_types  = Column(JSONB, default=lambda: ["helmet", "vest"])
    cooldown_seconds    = Column(Integer, default=120)
    required_consecutive_frames = Column(Integer, default=3)
    low_confidence_floor        = Column(Float, default=0.40)
    version             = Column(Integer, default=1, nullable=False)


class PpeType(BaseEntity):
    """Enterprise-defined catalog of PPE items — lets an enterprise add its
    own mandatory-PPE categories at runtime instead of being limited to a
    hardcoded set. zone_configs.required_ppe_types and cameras.ppe_overrides
    reference these by `code`. Actual detectability of a type still depends
    on what the AI worker's loaded model can recognize."""
    __tablename__ = "ppe_types"

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    code            = Column(String(50), nullable=False)
    name            = Column(String(100), nullable=False)


class ZoneRule(BaseEntity):
    __tablename__ = "zone_rules"
    __table_args__ = {"schema": "config"}

    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    zone_id             = Column(BigInteger, ForeignKey("zones.id"), nullable=True, index=True)
    rule_name           = Column(String(200), nullable=False)
    condition_type      = Column(String(100), nullable=False)
    duration_seconds    = Column(Integer, default=3)
    cooldown_seconds    = Column(Integer, default=120)
    severity            = Column(String(20), default="High")
    enabled             = Column(Boolean, default=True)
    actions             = Column(JSONB, default=lambda: ["CREATE_ALERT", "STORE_SNAPSHOT"])
    notify_roles        = Column(JSONB, default=lambda: ["Supervisor"])
    notify_channels     = Column(JSONB, default=lambda: ["Email", "InApp"])


class ConfigHistory(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "config_history"
    __table_args__ = (
        Index("ix_config_history_zone", "zone_id", "created_at"),
        {"schema": "config"},
    )

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    zone_id         = Column(BigInteger, ForeignKey("zones.id"), nullable=True)
    old_config      = Column(JSONB, nullable=True)
    new_config      = Column(JSONB, nullable=False)
    change_reason   = Column(Text, nullable=True)


# ─── Reports ──────────────────────────────────────────────────────────────────

class Report(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_enterprise", "enterprise_id", "created_at"),
        {"schema": "reports"},
    )

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True)
    report_type     = Column(String(50), nullable=False)
    format          = Column(String(10), nullable=False)
    from_date       = Column(DateTime(timezone=True), nullable=False)
    to_date         = Column(DateTime(timezone=True), nullable=False)
    object_key      = Column(String(500), nullable=True)
    status          = Column(String(20), default="Completed", nullable=False)
    generated_by    = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)


# ─── Shifts ───────────────────────────────────────────────────────────────────

class Shift(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "shifts"

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    factory_id      = Column(BigInteger, ForeignKey("factories.id"), nullable=True, index=True)
    name            = Column(String(100), nullable=False)
    start_time      = Column(Time, nullable=False)
    end_time        = Column(Time, nullable=False)
    days            = Column(JSONB, default=lambda: ["MON", "TUE", "WED", "THU", "FRI"])
    status          = Column(String(20), default="Active")


# ─── Occupancy ────────────────────────────────────────────────────────────────

class OccupancyLog(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "logs"
    __table_args__ = (
        Index("ix_occupancy_zone_ts", "zone_id", "timestamp"),
        {"schema": "occupancy"},
    )

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    zone_id         = Column(BigInteger, ForeignKey("zones.id"), nullable=True)
    camera_id       = Column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    current_count   = Column(Integer, nullable=False)
    shift_id        = Column(BigInteger, ForeignKey("shifts.id"), nullable=True)
    timestamp       = Column(DateTime(timezone=True), nullable=False, index=True)


# ─── PPE Violations ───────────────────────────────────────────────────────────

class PPEViolation(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "violations"
    __table_args__ = (
        Index("ix_violation_zone_ts", "zone_id", "created_at"),
        {"schema": "ppe"},
    )

    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    zone_id             = Column(BigInteger, ForeignKey("zones.id"), nullable=True, index=True)
    camera_id           = Column(BigInteger, ForeignKey("cameras.id"), nullable=True, index=True)
    violation_type      = Column(String(50), nullable=False)
    confidence          = Column(Float, nullable=False)
    snapshot_key        = Column(String(500))
    track_id            = Column(String(100))
    shift_id            = Column(BigInteger, ForeignKey("shifts.id"), nullable=True)
    rule_id             = Column(BigInteger, ForeignKey("config.zone_rules.id"), nullable=True)
    is_false_positive   = Column(Boolean, default=False)
    fp_reason           = Column(String(200), nullable=True)
    needs_review        = Column(Boolean, default=False, nullable=False)
    bbox                = Column(JSONB, nullable=True)


# ─── Alerts ───────────────────────────────────────────────────────────────────

class Alert(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alert_enterprise_status", "enterprise_id", "status"),
        {"schema": "alerts"},
    )

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    factory_id      = Column(BigInteger, ForeignKey("factories.id"), nullable=True)
    department_id   = Column(BigInteger, ForeignKey("departments.id"), nullable=True)
    zone_id         = Column(BigInteger, ForeignKey("zones.id"), nullable=True)
    camera_id       = Column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    violation_id    = Column(BigInteger, ForeignKey("ppe.violations.id"), nullable=True)
    alert_number    = Column(String(30), unique=True, nullable=False)
    alert_type      = Column(String(100), nullable=False)
    severity        = Column(String(20), nullable=False)
    status          = Column(String(30), default="Open", nullable=False)
    assigned_to     = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    shift_id        = Column(BigInteger, ForeignKey("shifts.id"), nullable=True)
    sla_due_at      = Column(DateTime(timezone=True), nullable=True)
    acknowledged_on = Column(DateTime(timezone=True), nullable=True)
    resolved_on     = Column(DateTime(timezone=True), nullable=True)
    # 'system' (AI-worker-generated) or a user's public_id — distinct from
    # BaseEntity.created_by, which records the acting *API caller* if any.
    created_source  = Column(String(100), default="system")


class AlertHistory(BaseEntity):
    __tablename__ = "alert_history"
    __table_args__ = {"schema": "alerts"}

    alert_id    = Column(BigInteger, ForeignKey("alerts.alerts.id"), nullable=True, index=True)
    from_status = Column(String(30))
    to_status   = Column(String(30))
    comment     = Column(Text)


# ─── Notifications ────────────────────────────────────────────────────────────

class NotificationLog(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "notification_log"
    __table_args__ = {"schema": "notifications"}

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    alert_id        = Column(BigInteger, ForeignKey("alerts.alerts.id"), nullable=True)
    channel         = Column(String(30), nullable=False)
    recipient_id    = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    sent_at         = Column(DateTime(timezone=True))
    status          = Column(String(20), default="Sent")
    failure_reason  = Column(Text, nullable=True)
    retry_count     = Column(Integer, default=0)


class NotificationRecipient(BaseEntity):
    """
    Who gets notified (email + desktop) when a violation/alert fires in a
    zone. zone_id=NULL means an enterprise-wide fallback recipient (used
    when a zone has no recipients configured of its own). `level` orders
    recipients for future time-based escalation (Phase 2) — for now every
    configured recipient for the zone is notified immediately.
    """
    __tablename__ = "notification_recipients"
    __table_args__ = {"schema": "notifications"}

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    zone_id         = Column(BigInteger, ForeignKey("zones.id"), nullable=True, index=True)
    user_id         = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    level           = Column(Integer, default=1, nullable=False)
    notify_email    = Column(Boolean, default=True, nullable=False)
    notify_desktop  = Column(Boolean, default=True, nullable=False)


class NotificationDelivery(BaseEntity):
    """Durable outbox; creation commits in the same transaction as the alert."""
    __tablename__ = "deliveries"
    __table_args__ = (
        Index("ix_deliveries_due", "status", "next_attempt_at"),
        Index("ix_deliveries_enterprise_created", "enterprise_id", "created_at"),
        {"schema": "notifications"},
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    enterprise_id = Column(BigInteger, ForeignKey("enterprises.id"), nullable=False)
    alert_id = Column(BigInteger, ForeignKey("alerts.alerts.id"), nullable=False)
    recipient_id = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    delivery_key = Column(String(160), unique=True, nullable=False)
    channel = Column(String(30), nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="Pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(200), nullable=True)


# ─── Audit ────────────────────────────────────────────────────────────────────

class AuditLog(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_enterprise_ts", "enterprise_id", "timestamp"),
        {"schema": "audit"},
    )

    enterprise_id   = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    user_id         = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    action          = Column(String(100), nullable=False)
    entity_type     = Column(String(100))
    # The audited entity's public_id (string) — audit_log intentionally
    # doesn't FK this, since it can point at any table's row.
    entity_id       = Column(String(36), nullable=True)
    old_value       = Column(JSONB)
    new_value       = Column(JSONB)
    ip_address      = Column(String(50))
    user_agent      = Column(Text)
    correlation_id  = Column(String(100))
    timestamp       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─── Camera Maintenance ───────────────────────────────────────────────────────

class CameraMaintenance(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "camera_maintenance"

    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True, index=True)
    camera_id           = Column(BigInteger, ForeignKey("cameras.id"), nullable=True, index=True)
    scheduled_date      = Column(Date)
    maintenance_type    = Column(String(50))
    assigned_to         = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    status              = Column(String(30), default="Scheduled")
    notes               = Column(Text)
    completed_at        = Column(DateTime(timezone=True), nullable=True)
    completed_by        = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    completion_notes    = Column(Text, nullable=True)
    next_due_date       = Column(Date, nullable=True)


# ─── Onboarding ───────────────────────────────────────────────────────────────

class SetupProgress(BaseEntity):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __tablename__ = "setup_progress"
    __table_args__ = {"schema": "onboarding"}

    user_id             = Column(BigInteger, ForeignKey("identity.users.id"), nullable=True)
    enterprise_id       = Column(BigInteger, ForeignKey("enterprises.id"), nullable=True)
    last_completed_step = Column(Integer, default=0)
    factory_id          = Column(BigInteger, ForeignKey("factories.id"), nullable=True)
    department_id       = Column(BigInteger, ForeignKey("departments.id"), nullable=True)
    zone_id             = Column(BigInteger, ForeignKey("zones.id"), nullable=True)
    camera_id           = Column(BigInteger, ForeignKey("cameras.id"), nullable=True)
    completed_at        = Column(DateTime(timezone=True), nullable=True)


class EventReceipt(Base):
    __tablename__ = "event_receipts"
    event_id = Column(String(36), primary_key=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
