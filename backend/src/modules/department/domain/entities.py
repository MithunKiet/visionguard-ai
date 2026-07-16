from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only=True)
class DepartmentEntity:
    enterprise_id: str
    factory_id: str
    name: str
    code: str
    id: str | None = None  # public_id — unset until persisted
    status: str = "Active"
    head_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
