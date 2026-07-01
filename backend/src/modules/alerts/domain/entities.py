from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class AlertEntity:
    id: UUID
    enterprise_id: UUID
    factory_id: UUID
    zone_id: UUID
    camera_id: UUID
    alert_number: str
    alert_type: str
    severity: str              # Critical / High / Medium / Low
    status: str                # Open / Acknowledged / Resolved / FalsePositive
    violation_id: UUID | None
    department_id: UUID | None
    assigned_to: UUID | None
    shift_id: UUID | None
    sla_due_at: datetime | None
    created_on: datetime
    acknowledged_on: datetime | None
    resolved_on: datetime | None
    created_by: str = "system"
