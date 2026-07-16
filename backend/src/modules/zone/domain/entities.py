from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only=True)
class ZoneEntity:
    enterprise_id: str
    factory_id: str
    department_id: str
    name: str
    code: str
    max_occupancy: int
    id: str | None = None  # public_id — unset until persisted
    status: str = "Active"
    zone_type: str = "Production"
    is_restricted: bool = False
    supervisor_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
