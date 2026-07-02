from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class CreateCameraRequest(BaseModel):
    factory_id: UUID
    zone_id: UUID
    name: str
    code: str
    rtsp_url: str
    camera_type: str = "Fixed"
    position_desc: str | None = None
    fps: float | None = None


class UpdateCameraRequest(BaseModel):
    name: str | None = None
    rtsp_url: str | None = None
    camera_type: str | None = None
    position_desc: str | None = None
    fps: float | None = None


class TestConnectionRequest(BaseModel):
    rtsp_url: str


class CameraResponse(BaseModel):
    id: UUID
    enterprise_id: UUID
    factory_id: UUID
    zone_id: UUID
    worker_id: UUID | None
    name: str
    code: str
    rtsp_url: str
    camera_type: str
    position_desc: str | None
    status: str
    fps: float | None
    in_maintenance: bool
    last_seen_at: datetime | None

    class Config:
        from_attributes = True


class RtspTestResponse(BaseModel):
    reachable: bool
    latency_ms: int
    rtsp_url: str
    status: str


class CameraHealthResponse(BaseModel):
    camera_id: str
    name: str
    status: str
    in_maintenance: bool
    last_seen_at: str | None
    rtsp_reachable: bool
    rtsp_latency_ms: int
