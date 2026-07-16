from datetime import date, datetime

from pydantic import BaseModel, Field


class ScheduleMaintenanceRequest(BaseModel):
    camera_id: str
    scheduled_date: date
    maintenance_type: str = Field(min_length=1, max_length=50)
    assigned_to: str | None = None
    notes: str | None = None


class CompleteMaintenanceRequest(BaseModel):
    completion_notes: str | None = None
    next_due_date: date | None = None


class EnableMaintenanceModeRequest(BaseModel):
    until: datetime | None = None
    reason: str | None = None
