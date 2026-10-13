"""
Recipient configuration CRUD. Alert sends are owned by the durable outbox.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.domain.entities import NotificationRecipientEntity
from src.modules.notifications.infrastructure.repositories import NotificationRecipientRepository



class NotificationService:

    def __init__(self, repo: NotificationRecipientRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    # ── Recipient config CRUD ───────────────────────────────────────────────

    async def list_recipients(self, enterprise_id: str, zone_id: str | None = None) -> list[dict]:
        recipients = await self._repo.list(enterprise_id, zone_id)
        return [self._to_dict(r) for r in recipients]

    async def add_recipient(
        self, enterprise_id: str, user_id: str, zone_id: str | None,
        level: int, notify_email: bool, notify_desktop: bool,
    ) -> dict:
        entity = NotificationRecipientEntity(
            enterprise_id=enterprise_id, zone_id=zone_id,
            user_id=user_id, level=level, notify_email=notify_email, notify_desktop=notify_desktop,
        )
        return self._to_dict(await self._repo.create(entity))

    async def remove_recipient(self, recipient_id: str, enterprise_id: str) -> None:
        await self._repo.delete(recipient_id, enterprise_id)

    @staticmethod
    def _to_dict(r: NotificationRecipientEntity) -> dict:
        return {
            "id": r.id,
            "enterprise_id": r.enterprise_id,
            "zone_id": r.zone_id,
            "user_id": r.user_id,
            "level": r.level,
            "notify_email": r.notify_email,
            "notify_desktop": r.notify_desktop,
        }
