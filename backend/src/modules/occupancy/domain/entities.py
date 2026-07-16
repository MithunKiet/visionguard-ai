from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only=True)
class OccupancyLogEntity:
    enterprise_id: str
    zone_id: str
    camera_id: str
    current_count: int
    timestamp: datetime
    id: str | None = None  # public_id — unset until persisted
    shift_id: str | None = None
