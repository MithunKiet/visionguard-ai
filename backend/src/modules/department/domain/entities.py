from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class DepartmentEntity:
    id: UUID
    enterprise_id: UUID
    factory_id: UUID
    name: str
    code: str
    status: str = "Active"
    head_user_id: UUID | None = None
    created_on: datetime | None = None
    modified_on: datetime | None = None
    deleted_at: datetime | None = None
