from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only=True)
class AlertEntity:
    enterprise_id: str
    factory_id: str
    zone_id: str
    camera_id: str
    alert_number: str
    alert_type: str
    severity: str              # Critical / High / Medium / Low
    status: str                # Open / Acknowledged / Resolved / FalsePositive
    created_at: datetime
    id: str | None = None      # public_id — unset until persisted
    violation_id: str | None = None
    department_id: str | None = None
    assigned_to: str | None = None
    shift_id: str | None = None
    sla_due_at: datetime | None = None
    acknowledged_on: datetime | None = None
    resolved_on: datetime | None = None
    created_by: str = "system"
