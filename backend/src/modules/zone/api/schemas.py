from pydantic import BaseModel, Field


class CreateZoneRequest(BaseModel):
    # factory_id is intentionally not accepted here — it's derived
    # server-side from department_id so a zone can never be created under a
    # factory that doesn't match its department (see ZoneService.create_zone).
    department_id: str
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    max_occupancy: int = Field(ge=1)
    zone_type: str = "Production"
    is_restricted: bool = False
    supervisor_id: str | None = None
    required_ppe_types: list[str] | None = None


class UpdateZoneRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    max_occupancy: int | None = Field(None, ge=1)
    zone_type: str | None = None
    is_restricted: bool | None = None
    supervisor_id: str | None = None
    status: str | None = None
