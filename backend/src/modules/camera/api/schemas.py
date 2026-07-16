from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class CreateCameraRequest(BaseModel):
    # factory_id is intentionally not accepted here — it's derived
    # server-side from zone_id so a camera can never be created under a
    # factory that doesn't match its zone (see CameraService.create_camera).
    zone_id: str
    name: str
    code: str
    rtsp_url: str
    camera_type: str = "Fixed"
    position_desc: str | None = None
    fps: float | None = None
    # PPE overrides for this specific camera, keyed by ppe_types.code — omit
    # a code (or the whole field) to inherit the zone's setting for it.
    ppe_overrides: dict[str, bool] | None = None


class UpdateCameraRequest(BaseModel):
    name: str | None = None
    rtsp_url: str | None = None
    camera_type: str | None = None
    position_desc: str | None = None
    fps: float | None = None
    # Partial patch, merged into the camera's existing overrides — codes not
    # present here are left untouched. A code mapped to `null` clears that
    # override (reverts to inheriting the zone's setting for it).
    ppe_overrides: dict[str, bool | None] | None = None


class TestConnectionRequest(BaseModel):
    rtsp_url: str


class UpdateCameraStatusRequest(BaseModel):
    """Manual on/off toggle — hot-applied to the assigned AI worker, no restart."""
    status: Literal["Active", "Inactive"]


class CameraResponse(BaseModel):
    id: str
    enterprise_id: str
    factory_id: str
    zone_id: str
    worker_id: str | None
    name: str
    code: str
    rtsp_url: str
    camera_type: str
    position_desc: str | None
    status: str
    fps: float | None
    in_maintenance: bool
    last_seen_at: datetime | None
    ppe_overrides: dict[str, bool]
    enforces: list[str]

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
