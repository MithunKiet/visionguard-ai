from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class WorkerSchedulingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: UUID
    max_cameras: int = Field(ge=1, le=10000, strict=True)


class HeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    worker_id: str
    hostname: str | None = None
    model_version: str | None = None
    gpu_available: bool = False


class DetectionHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inference_age_seconds: float | None = Field(..., ge=0, le=30, allow_inf_nan=False, strict=True)


class ConfigApplication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_id: UUID
    zone_id: UUID
    lease_token: UUID
    version: int = Field(ge=1, strict=True)
    detection_health: DetectionHealth | None = None


class ConfigApplicationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applications: list[ConfigApplication] = Field(min_length=1, max_length=200)


class WorkerResponse(BaseModel):
    id: str
    enterprise_id: str
    worker_id: str
    hostname: str | None
    status: str
    model_version: str | None
    gpu_available: bool
    last_heartbeat: datetime | None
    is_alive: bool
    factory_id: str | None = None
    max_cameras: int = 0
