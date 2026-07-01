from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class AlertOut(BaseModel):
    id: str
    enterprise_id: str
    factory_id: str
    zone_id: str
    camera_id: str
    violation_id: str | None
    alert_number: str
    alert_type: str
    severity: str
    status: str
    assigned_to: str | None
    shift_id: str | None
    sla_due_at: str | None
    created_on: str
    acknowledged_on: str | None
    resolved_on: str | None


class AcknowledgeRequest(BaseModel):
    pass


class ResolveRequest(BaseModel):
    note: str | None = None


class FalsePositiveRequest(BaseModel):
    reason: str


class AssignRequest(BaseModel):
    user_id: UUID
