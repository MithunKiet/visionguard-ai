from dataclasses import dataclass, field
from datetime import datetime


@dataclass(kw_only=True)
class CameraEntity:
    enterprise_id: str
    factory_id: str
    zone_id: str
    name: str
    code: str
    rtsp_url: str
    status: str                        # Active / Offline / Degraded / Maintenance
    id: str | None = None              # public_id — unset until persisted
    camera_type: str = "Fixed"
    position_desc: str | None = None
    fps: float | None = None
    worker_id: str | None = None
    in_maintenance: bool = False
    maintenance_until: datetime | None = None
    last_seen_at: datetime | None = None
    deleted_at: datetime | None = None
    # Per-camera PPE overrides keyed by ppe_types.code, e.g. {"gloves": True}.
    # A code absent here inherits its zone's setting for that code.
    ppe_overrides: dict = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == "Active" and not self.in_maintenance and self.deleted_at is None
