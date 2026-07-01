from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class CameraEntity:
    id: UUID
    enterprise_id: UUID
    factory_id: UUID
    zone_id: UUID
    name: str
    code: str
    rtsp_url: str
    status: str                        # Active / Offline / Degraded / Maintenance
    camera_type: str = "Fixed"
    position_desc: str | None = None
    fps: float | None = None
    worker_id: UUID | None = None
    in_maintenance: bool = False
    maintenance_until: datetime | None = None
    last_seen_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == "Active" and not self.in_maintenance and self.deleted_at is None
