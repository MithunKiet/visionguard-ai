"""
All SQLAlchemy ORM models — single source of truth for Alembic migrations.
Every table follows the DB schema in AI_MASTER_CONTEXT.md Section 6.
"""
import uuid
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, Date,
    DateTime, Time, ForeignKey, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.shared.database.session import Base


# ─── Enterprises ─────────────────────────────────────────────────────────────

class Enterprise(Base):
    __tablename__ = "enterprises"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    created_on      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─── Identity ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    name                = Column(String(200), nullable=False)
    email               = Column(String(200), unique=True, nullable=False)
    password_hash       = Column(String(500), nullable=False)
    role                = Column(String(50), nullable=False)
    factory_id          = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=True)
    department_id       = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    assigned_zone_ids   = Column(JSONB, default=list)
    status              = Column(String(20), default="Active", nullable=False)
    is_first_login      = Column(Boolean, default=True, nullable=False)
    setup_completed     = Column(Boolean, default=False, nullable=False)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    master_password_hash = Column(String(500), nullable=True)
    totp_enabled        = Column(Boolean, default=False, nullable=False)
    dnd_enabled         = Column(Boolean, default=False, nullable=False)
    dnd_start           = Column(Time, nullable=True)
    dnd_end             = Column(Time, nullable=True)
    notification_prefs  = Column(JSONB, default=dict)
    session_timeout_min = Column(Integer, nullable=True)
    last_login_at       = Column(DateTime(timezone=True), nullable=True)
    invited_by          = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    invited_at          = Column(DateTime(timezone=True), nullable=True)
    created_on          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at          = Column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "identity"}

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True)
    token_hash  = Column(String(500), nullable=False, unique=True)
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    revoked     = Column(Boolean, default=False, nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─── Factories ───────────────────────────────────────────────────────────────

class Factory(Base):
    __tablename__ = "factories"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    code            = Column(String(50), nullable=False)
    location        = Column(String(300))
    plant_head_id   = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    status          = Column(String(20), default="Active", nullable=False)
    created_on      = Column(DateTime(timezone=True), server_default=func.now())
    modified_on     = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)
    version         = Column(Integer, default=1)


class Department(Base):
    __tablename__ = "departments"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id      = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    code            = Column(String(50), nullable=False)
    head_user_id    = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    status          = Column(String(20), default="Active", nullable=False)
    created_on      = Column(DateTime(timezone=True), server_default=func.now())
    modified_on     = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)
    version         = Column(Integer, default=1)


class Zone(Base):
    __tablename__ = "zones"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id      = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=False, index=True)
    department_id   = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    code            = Column(String(50), nullable=False)
    max_occupancy   = Column(Integer, nullable=False)
    supervisor_id   = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    zone_type       = Column(String(50), default="Production")
    is_restricted   = Column(Boolean, default=False)
    status          = Column(String(20), default="Active", nullable=False)
    created_on      = Column(DateTime(timezone=True), server_default=func.now())
    modified_on     = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)
    version         = Column(Integer, default=1)


# ─── Workers ─────────────────────────────────────────────────────────────────

class AIWorker(Base):
    __tablename__ = "ai_workers"
    __table_args__ = {"schema": "worker"}

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    worker_id       = Column(String(100), unique=True, nullable=False)
    hostname        = Column(String(200))
    status          = Column(String(20), default="Online")
    model_version   = Column(String(50))
    last_heartbeat  = Column(DateTime(timezone=True))
    gpu_available   = Column(Boolean, default=False)
    created_on      = Column(DateTime(timezone=True), server_default=func.now())


# ─── Cameras ─────────────────────────────────────────────────────────────────

class Camera(Base):
    __tablename__ = "cameras"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id          = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=False, index=True)
    zone_id             = Column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False, index=True)
    worker_id           = Column(UUID(as_uuid=True), ForeignKey("worker.ai_workers.id"), nullable=True)
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
    created_on          = Column(DateTime(timezone=True), server_default=func.now())
    modified_on         = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at          = Column(DateTime(timezone=True), nullable=True)
    version             = Column(Integer, default=1)


# ─── Config ───────────────────────────────────────────────────────────────────

class ZoneConfig(Base):
    __tablename__ = "zone_configs"
    __table_args__ = {"schema": "config"}

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    zone_id             = Column(UUID(as_uuid=True), ForeignKey("zones.id"), unique=True, nullable=False)
    person_threshold    = Column(Float, default=0.70)
    helmet_threshold    = Column(Float, default=0.75)
    vest_threshold      = Column(Float, default=0.75)
    gloves_threshold    = Column(Float, default=0.70)
    shoes_threshold     = Column(Float, default=0.70)
    mask_threshold      = Column(Float, default=0.75)
    max_occupancy       = Column(Integer)
    frame_sample_fps    = Column(Integer, default=2)
    ppe_required        = Column(JSONB, default=lambda: ["helmet", "vest"])
    cooldown_seconds    = Column(Integer, default=120)
    updated_by          = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    updated_at          = Column(DateTime(timezone=True))
    version             = Column(Integer, default=1, nullable=False)


class ZoneRule(Base):
    __tablename__ = "zone_rules"
    __table_args__ = {"schema": "config"}

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    zone_id             = Column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False, index=True)
    rule_name           = Column(String(200), nullable=False)
    condition_type      = Column(String(100), nullable=False)
    duration_seconds    = Column(Integer, default=3)
    cooldown_seconds    = Column(Integer, default=120)
    severity            = Column(String(20), default="High")
    enabled             = Column(Boolean, default=True)
    actions             = Column(JSONB, default=lambda: ["CREATE_ALERT", "STORE_SNAPSHOT"])
    notify_roles        = Column(JSONB, default=lambda: ["Supervisor"])
    notify_channels     = Column(JSONB, default=lambda: ["Email", "InApp"])
    created_by          = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    created_on          = Column(DateTime(timezone=True), server_default=func.now())


# ─── Shifts ───────────────────────────────────────────────────────────────────

class Shift(Base):
    __tablename__ = "shifts"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id      = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=False, index=True)
    name            = Column(String(100), nullable=False)
    start_time      = Column(Time, nullable=False)
    end_time        = Column(Time, nullable=False)
    days            = Column(JSONB, default=lambda: ["MON", "TUE", "WED", "THU", "FRI"])
    status          = Column(String(20), default="Active")


# ─── Occupancy ────────────────────────────────────────────────────────────────

class OccupancyLog(Base):
    __tablename__ = "logs"
    __table_args__ = (
        Index("ix_occupancy_zone_ts", "zone_id", "timestamp"),
        {"schema": "occupancy"},
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    zone_id         = Column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    camera_id       = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False)
    current_count   = Column(Integer, nullable=False)
    shift_id        = Column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=True)
    timestamp       = Column(DateTime(timezone=True), nullable=False, index=True)


# ─── PPE Violations ───────────────────────────────────────────────────────────

class PPEViolation(Base):
    __tablename__ = "violations"
    __table_args__ = (
        Index("ix_violation_zone_ts", "zone_id", "created_on"),
        {"schema": "ppe"},
    )

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    zone_id             = Column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False, index=True)
    camera_id           = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True)
    violation_type      = Column(String(50), nullable=False)
    confidence          = Column(Float, nullable=False)
    snapshot_key        = Column(String(500))
    track_id            = Column(String(100))
    shift_id            = Column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=True)
    rule_id             = Column(UUID(as_uuid=True), ForeignKey("config.zone_rules.id"), nullable=True)
    is_false_positive   = Column(Boolean, default=False)
    fp_reason           = Column(String(200), nullable=True)
    created_on          = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─── Alerts ───────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alert_enterprise_status", "enterprise_id", "status"),
        {"schema": "alerts"},
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    factory_id      = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=False)
    department_id   = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    zone_id         = Column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False)
    camera_id       = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False)
    violation_id    = Column(UUID(as_uuid=True), ForeignKey("ppe.violations.id"), nullable=True)
    alert_number    = Column(String(30), unique=True, nullable=False)
    alert_type      = Column(String(100), nullable=False)
    severity        = Column(String(20), nullable=False)
    status          = Column(String(30), default="Open", nullable=False)
    assigned_to     = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    shift_id        = Column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=True)
    sla_due_at      = Column(DateTime(timezone=True), nullable=True)
    created_on      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_on = Column(DateTime(timezone=True), nullable=True)
    resolved_on     = Column(DateTime(timezone=True), nullable=True)
    created_by      = Column(String(100), default="system")


class AlertHistory(Base):
    __tablename__ = "alert_history"
    __table_args__ = {"schema": "alerts"}

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id    = Column(UUID(as_uuid=True), ForeignKey("alerts.alerts.id"), nullable=False, index=True)
    from_status = Column(String(30))
    to_status   = Column(String(30))
    changed_by  = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    changed_at  = Column(DateTime(timezone=True), server_default=func.now())
    comment     = Column(Text)


# ─── Notifications ────────────────────────────────────────────────────────────

class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = {"schema": "notifications"}

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    alert_id        = Column(UUID(as_uuid=True), ForeignKey("alerts.alerts.id"), nullable=True)
    channel         = Column(String(30), nullable=False)
    recipient_id    = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    sent_at         = Column(DateTime(timezone=True))
    status          = Column(String(20), default="Sent")
    failure_reason  = Column(Text, nullable=True)
    retry_count     = Column(Integer, default=0)


# ─── Audit ────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_enterprise_ts", "enterprise_id", "timestamp"),
        {"schema": "audit"},
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id   = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    action          = Column(String(100), nullable=False)
    entity_type     = Column(String(100))
    entity_id       = Column(UUID(as_uuid=True), nullable=True)
    old_value       = Column(JSONB)
    new_value       = Column(JSONB)
    ip_address      = Column(String(50))
    user_agent      = Column(Text)
    correlation_id  = Column(String(100))
    timestamp       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ─── Camera Maintenance ───────────────────────────────────────────────────────

class CameraMaintenance(Base):
    __tablename__ = "camera_maintenance"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False, index=True)
    camera_id           = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True)
    scheduled_date      = Column(Date)
    maintenance_type    = Column(String(50))
    assigned_to         = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    status              = Column(String(30), default="Scheduled")
    notes               = Column(Text)
    completed_at        = Column(DateTime(timezone=True), nullable=True)
    completed_by        = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True)
    completion_notes    = Column(Text, nullable=True)
    next_due_date       = Column(Date, nullable=True)


# ─── Onboarding ───────────────────────────────────────────────────────────────

class SetupProgress(Base):
    __tablename__ = "setup_progress"
    __table_args__ = {"schema": "onboarding"}

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id             = Column(UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False)
    enterprise_id       = Column(UUID(as_uuid=True), ForeignKey("enterprises.id"), nullable=False)
    last_completed_step = Column(Integer, default=0)
    factory_id          = Column(UUID(as_uuid=True), ForeignKey("factories.id"), nullable=True)
    department_id       = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    zone_id             = Column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    camera_id           = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    completed_at        = Column(DateTime(timezone=True), nullable=True)
