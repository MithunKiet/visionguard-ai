from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class HeartbeatRequest(BaseModel):
    worker_id: str
    hostname: str | None = None
    model_version: str | None = None
    gpu_available: bool = False


class WorkerResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    worker_id: str
    hostname: str | None
    status: str
    model_version: str | None
    gpu_available: bool
    last_heartbeat: datetime | None
    is_alive: bool
