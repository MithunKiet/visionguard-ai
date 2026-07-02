from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleMaintenanceRequest(BaseModel):
    camera_id: UUID
    scheduled_date: date
    maintenance_type: str = Field(min_length=1, max_length=50)
    assigned_to: UUID | None = None
    notes: str | None = None


class CompleteMaintenanceRequest(BaseModel):
    completion_notes: str | None = None
    next_due_date: date | None = None


class EnableMaintenanceModeRequest(BaseModel):
    until: datetime | None = None
    reason: str | None = None
