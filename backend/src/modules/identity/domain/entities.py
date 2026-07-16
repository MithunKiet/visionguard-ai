from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UserEntity:
    id: str  # public_id
    enterprise_id: str  # enterprise's public_id
    name: str
    email: str
    roles: list[str]
    status: str
    password_hash: str
    is_first_login: bool = True
    totp_enabled: bool = False
    last_login_at: datetime | None = None
    deleted_at: datetime | None = None
    # Data-visibility scope — which factory/department/zones this user is
    # restricted to (see shared/security/scope.py). None/[] means "not
    # scoped at this level"; roles like SYSTEM_ADMIN/ENTERPRISE_ADMIN
    # ignore these entirely and see everything in the enterprise.
    factory_id: str | None = None
    department_id: str | None = None
    assigned_zone_ids: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.status == "Active" and self.deleted_at is None
