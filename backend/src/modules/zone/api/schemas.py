from uuid import UUID

from pydantic import BaseModel, Field


class CreateZoneRequest(BaseModel):
    factory_id: UUID
    department_id: UUID
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    max_occupancy: int = Field(ge=1)
    zone_type: str = "Production"
    is_restricted: bool = False
    supervisor_id: UUID | None = None
    ppe_required: list[str] | None = None


class UpdateZoneRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    max_occupancy: int | None = Field(None, ge=1)
    zone_type: str | None = None
    is_restricted: bool | None = None
    supervisor_id: UUID | None = None
    status: str | None = None
