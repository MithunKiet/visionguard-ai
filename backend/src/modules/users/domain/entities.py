from dataclasses import dataclass, field
from datetime import datetime


@dataclass(kw_only=True)
class UserAdminEntity:
    """A user as seen by enterprise/factory administrators managing accounts
    — distinct from identity.domain.entities.UserEntity, which is shaped for
    the auth/login path (carries password_hash, no display names for
    factory/department)."""
    enterprise_id: str
    name: str
    email: str
    id: str | None = None          # public_id — unset until persisted
    status: str = "Active"
    roles: list[str] = field(default_factory=list)
    factory_id: str | None = None
    factory_name: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    assigned_zone_ids: list[str] = field(default_factory=list)
    is_first_login: bool = True
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == "Active" and self.deleted_at is None
