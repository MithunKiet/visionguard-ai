"""
Base entity with standard columns required on every table.

Per AGENTS.md, every table must include:
- PublicId (GUID) — used for all external API communication
- IsActive (soft delete flag)
- IsApproved
- CreatedBy, CreatedAt, UpdatedBy, UpdatedAt
- DeletedBy, DeletedAt (populated when soft-deleted / deactivated)
- DeveloperRemark

Internal `id` (integer PK) is never exposed via APIs.
"""

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# IST timezone (UTC+5:30) — all timestamps in IST per AGENTS.md
IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    """Return current datetime in IST."""
    return datetime.now(IST)


def _generate_public_id() -> str:
    """Generate a new UUID string for PublicId."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""

    pass


class BaseEntity(Base):
    """
    Abstract base entity — inherited by all domain models.

    Provides the standard columns mandated by the project conventions.
    Internal `id` is the database primary key (never exposed via API).
    `public_id` (UUID) is used for all external communication.
    """

    __abstract__ = True

    # ── Internal PK (never exposed) ──────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ── Public identifier (exposed via API) ──────────────────────
    public_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
        default=_generate_public_id,
        index=True,
    )

    # ── Soft delete & approval ───────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # ── Audit columns ────────────────────────────────────────────
    created_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_ist,
    )

    updated_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now_ist,
        onupdate=_now_ist,
    )

    # ── Soft-delete audit columns ───────────────────────────────
    deleted_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Developer notes ──────────────────────────────────────────
    developer_remark: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
