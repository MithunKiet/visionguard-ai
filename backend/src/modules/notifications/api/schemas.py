from pydantic import BaseModel


class AddRecipientRequest(BaseModel):
    user_id: str
    zone_id: str | None = None  # None = enterprise-wide fallback recipient
    level: int = 1
    notify_email: bool = True
    notify_desktop: bool = True
