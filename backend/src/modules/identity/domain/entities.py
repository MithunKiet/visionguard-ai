from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class UserEntity:
    id: UUID
    enterprise_id: UUID
    name: str
    email: str
    role: str
    status: str
    password_hash: str
    master_password_hash: str | None = None
    is_first_login: bool = True
    totp_enabled: bool = False
    last_login_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == "Active" and self.deleted_at is None
