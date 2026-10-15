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
