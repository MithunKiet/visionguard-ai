from dataclasses import dataclass


@dataclass(kw_only=True)
class NotificationRecipientEntity:
    enterprise_id: str
    user_id: str
    id: str | None = None  # public_id — unset until persisted
    zone_id: str | None = None
    level: int = 1
    notify_email: bool = True
    notify_desktop: bool = True
