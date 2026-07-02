from dataclasses import dataclass
from uuid import UUID


@dataclass
class NotificationRecipientEntity:
    id: UUID
    enterprise_id: UUID
    user_id: UUID
    zone_id: UUID | None = None
    level: int = 1
    notify_email: bool = True
    notify_desktop: bool = True
