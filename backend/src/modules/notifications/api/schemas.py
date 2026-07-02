from uuid import UUID
from pydantic import BaseModel


class AddRecipientRequest(BaseModel):
    user_id: UUID
    zone_id: UUID | None = None  # None = enterprise-wide fallback recipient
    level: int = 1
    notify_email: bool = True
    notify_desktop: bool = True
