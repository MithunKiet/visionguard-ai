"""
AlertService — create from violation events, lifecycle transitions, deduplication.
"""
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog

from src.core.exceptions import NotFoundException, VisionGuardException
from src.modules.alerts.domain.entities import AlertEntity
from src.modules.alerts.infrastructure.repositories import AlertRepository
from src.modules.ppe.domain.entities import ViolationEntity

log = structlog.get_logger()

# SLA minutes per severity
_SLA_MINUTES = {"Critical": 15, "High": 60, "Medium": 240, "Low": 1440}

# Violation type → severity + alert_type
_VIOLATION_META = {
    "helmet_missing":  ("Critical", "PPE_VIOLATION_HELMET"),
    "vest_missing":    ("High",     "PPE_VIOLATION_VEST"),
    "gloves_missing":  ("Medium",   "PPE_VIOLATION_GLOVES"),
    "shoes_missing":   ("Medium",   "PPE_VIOLATION_SHOES"),
    "mask_missing":    ("High",     "PPE_VIOLATION_MASK"),
}

_ALLOWED_TRANSITIONS = {
    "Open":         {"Acknowledged", "Resolved", "FalsePositive"},
    "Acknowledged": {"Resolved", "FalsePositive"},
    "Resolved":     set(),
    "FalsePositive": set(),
}


class AlertService:

    def __init__(self, repo: AlertRepository):
        self._repo = repo

    # ── Called by RabbitMQ consumer ────────────────────────────────────────

    async def create_from_violation(
        self,
        violation: ViolationEntity,
        factory_id: UUID,
        cooldown_seconds: int = 120,
    ) -> AlertEntity | None:
        severity, alert_type = _VIOLATION_META.get(
            violation.violation_type, ("High", f"PPE_{violation.violation_type.upper()}")
        )

        # Deduplication — skip if same alert already open within cooldown
        if await self._repo.exists_open(
            violation.zone_id, violation.camera_id, alert_type, cooldown_seconds
        ):
            log.debug("alert.deduplicated", type=alert_type, zone_id=str(violation.zone_id))
            return None

        seq = await self._repo.next_sequence(violation.enterprise_id)
        year = datetime.now(timezone.utc).year
        alert_number = f"ALT-{year}-{seq:05d}"

        now = datetime.now(timezone.utc)
        sla_due_at = now + timedelta(minutes=_SLA_MINUTES.get(severity, 60))

        entity = AlertEntity(
            id=uuid.uuid4(),
            enterprise_id=violation.enterprise_id,
            factory_id=factory_id,
            department_id=None,
            zone_id=violation.zone_id,
            camera_id=violation.camera_id,
            violation_id=violation.id,
            alert_number=alert_number,
            alert_type=alert_type,
            severity=severity,
            status="Open",
            assigned_to=None,
            shift_id=violation.shift_id,
            sla_due_at=sla_due_at,
            created_on=now,
            acknowledged_on=None,
            resolved_on=None,
        )
        alert = await self._repo.create(entity)
        log.info(
            "alert.created",
            alert_number=alert_number,
            severity=severity,
            type=alert_type,
        )
        return alert

    # ── API ────────────────────────────────────────────────────────────────

    async def list_alerts(
        self,
        enterprise_id: UUID,
        status: str | None = None,
        severity: str | None = None,
        zone_id: UUID | None = None,
        assigned_to: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        items, total = await self._repo.list(
            enterprise_id, status, severity, zone_id, assigned_to, page, page_size
        )
        return [self.to_dict(a) for a in items], total

    async def get_alert(self, alert_id: UUID, enterprise_id: UUID) -> dict:
        alert = await self._repo.get_by_id(alert_id, enterprise_id)
        if not alert:
            raise NotFoundException("Alert", str(alert_id))
        return self.to_dict(alert)

    async def acknowledge(self, alert_id: UUID, enterprise_id: UUID, user_id: UUID) -> dict:
        return self.to_dict(
            await self._transition(alert_id, enterprise_id, "Acknowledged", user_id)
        )

    async def resolve(
        self, alert_id: UUID, enterprise_id: UUID, user_id: UUID, note: str | None
    ) -> dict:
        return self.to_dict(
            await self._transition(alert_id, enterprise_id, "Resolved", user_id, note)
        )

    async def mark_false_positive(
        self, alert_id: UUID, enterprise_id: UUID, user_id: UUID, reason: str
    ) -> dict:
        return self.to_dict(
            await self._transition(alert_id, enterprise_id, "FalsePositive", user_id, reason)
        )

    async def assign(self, alert_id: UUID, enterprise_id: UUID, assign_to: UUID) -> dict:
        alert = await self._repo.get_by_id(alert_id, enterprise_id)
        if not alert:
            raise NotFoundException("Alert", str(alert_id))
        await self._repo.assign(alert_id, enterprise_id, assign_to)
        alert.assigned_to = assign_to
        return self.to_dict(alert)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _transition(
        self,
        alert_id: UUID,
        enterprise_id: UUID,
        to_status: str,
        changed_by: UUID,
        comment: str | None = None,
    ) -> AlertEntity:
        alert = await self._repo.get_by_id(alert_id, enterprise_id)
        if not alert:
            raise NotFoundException("Alert", str(alert_id))

        if to_status not in _ALLOWED_TRANSITIONS.get(alert.status, set()):
            raise VisionGuardException(
                code="INVALID_TRANSITION",
                message=f"Cannot move alert from '{alert.status}' to '{to_status}'",
                status_code=422,
            )
        return await self._repo.transition(alert_id, enterprise_id, to_status, changed_by, comment)

    @staticmethod
    def to_dict(a: AlertEntity) -> dict:
        return {
            "id": str(a.id),
            "enterprise_id": str(a.enterprise_id),
            "factory_id": str(a.factory_id),
            "zone_id": str(a.zone_id),
            "camera_id": str(a.camera_id),
            "violation_id": str(a.violation_id) if a.violation_id else None,
            "alert_number": a.alert_number,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "status": a.status,
            "assigned_to": str(a.assigned_to) if a.assigned_to else None,
            "shift_id": str(a.shift_id) if a.shift_id else None,
            "sla_due_at": a.sla_due_at.isoformat() if a.sla_due_at else None,
            "created_on": a.created_on.isoformat(),
            "acknowledged_on": a.acknowledged_on.isoformat() if a.acknowledged_on else None,
            "resolved_on": a.resolved_on.isoformat() if a.resolved_on else None,
        }
