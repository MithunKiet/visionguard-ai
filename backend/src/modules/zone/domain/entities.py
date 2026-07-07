from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ZoneEntity:
    id: UUID
    enterprise_id: UUID
    factory_id: UUID
    department_id: UUID
    name: str
    code: str
    max_occupancy: int
    status: str = "Active"
    zone_type: str = "Production"
    is_restricted: bool = False
    supervisor_id: UUID | None = None
    created_on: datetime | None = None
    modified_on: datetime | None = None
    deleted_at: datetime | None = None
