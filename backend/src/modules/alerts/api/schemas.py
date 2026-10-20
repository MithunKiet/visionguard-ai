from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints


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
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None


class FalsePositiveRequest(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class AssignRequest(BaseModel):
    user_id: str


class CorrectivePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_to: UUID
    due_at: AwareDatetime
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    expected_revision: int = Field(ge=0, strict=True)


class CompleteActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    expected_revision: int = Field(ge=0, strict=True)
