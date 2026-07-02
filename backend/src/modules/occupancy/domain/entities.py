from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class OccupancyLogEntity:
    id: UUID
    enterprise_id: UUID
    zone_id: UUID
    camera_id: UUID
    current_count: int
    shift_id: UUID | None
    timestamp: datetime
