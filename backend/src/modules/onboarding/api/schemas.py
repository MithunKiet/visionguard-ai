
from pydantic import BaseModel, Field


class SetupFactoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    location: str | None = Field(None, max_length=300)


class SetupDepartmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)


class SetupZoneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    max_occupancy: int = Field(ge=1)
    zone_type: str = "Production"
    is_restricted: bool = False
    ppe_required: list[str] = ["helmet", "vest"]


class SetupCameraRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    rtsp_url: str = Field(min_length=1, max_length=500)
    camera_type: str = "Fixed"
    position_desc: str | None = None
    # Section 18 — installer must confirm the camera placement checklist
    # (height 3-5m, tilt 30-45°, ≥1080p @ 15FPS, ≥150 LUX) before submitting.
    placement_confirmed: bool = False
