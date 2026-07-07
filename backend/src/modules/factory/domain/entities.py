from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class FactoryEntity:
    id: UUID
    enterprise_id: UUID
    name: str
    code: str
    status: str = "Active"
    location: str | None = None
    plant_head_id: UUID | None = None
    created_on: datetime | None = None
    modified_on: datetime | None = None
    deleted_at: datetime | None = None
