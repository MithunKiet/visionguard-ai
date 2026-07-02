from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.domain.entities import NotificationRecipientEntity
from src.shared.database.models import NotificationLog, NotificationRecipient


class NotificationRecipientRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(self, enterprise_id: UUID, zone_id: UUID | None = None) -> list[NotificationRecipientEntity]:
        q = select(NotificationRecipient).where(NotificationRecipient.enterprise_id == enterprise_id)
        if zone_id:
            q = q.where(NotificationRecipient.zone_id == zone_id)
        result = await self._db.execute(q.order_by(NotificationRecipient.level))
        return [self._to_entity(r) for r in result.scalars()]

    async def list_for_zone_with_fallback(self, enterprise_id: UUID, zone_id: UUID) -> list[NotificationRecipientEntity]:
        """Zone-specific recipients if any exist, else enterprise-wide (zone_id IS NULL) ones."""
        zone_recipients = await self.list(enterprise_id, zone_id)
        if zone_recipients:
            return zone_recipients

        result = await self._db.execute(
            select(NotificationRecipient).where(
                NotificationRecipient.enterprise_id == enterprise_id,
                NotificationRecipient.zone_id.is_(None),
            ).order_by(NotificationRecipient.level)
        )
        return [self._to_entity(r) for r in result.scalars()]

    async def create(self, entity: NotificationRecipientEntity) -> NotificationRecipientEntity:
        row = NotificationRecipient(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            zone_id=entity.zone_id,
            user_id=entity.user_id,
            level=entity.level,
            notify_email=entity.notify_email,
            notify_desktop=entity.notify_desktop,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def delete(self, recipient_id: UUID, enterprise_id: UUID) -> None:
        from sqlalchemy import delete
        await self._db.execute(
            delete(NotificationRecipient).where(
                NotificationRecipient.id == recipient_id,
                NotificationRecipient.enterprise_id == enterprise_id,
            )
        )
        await self._db.commit()

    async def log_delivery(
        self,
        enterprise_id: UUID,
        alert_id: UUID,
        recipient_id: UUID,
        channel: str,
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        self._db.add(NotificationLog(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            alert_id=alert_id,
            channel=channel,
            recipient_id=recipient_id,
            sent_at=datetime.now(timezone.utc),
            status=status,
            failure_reason=failure_reason,
        ))
        await self._db.commit()

    @staticmethod
    def _to_entity(row: NotificationRecipient) -> NotificationRecipientEntity:
        return NotificationRecipientEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            zone_id=row.zone_id,
            user_id=row.user_id,
            level=row.level,
            notify_email=row.notify_email,
            notify_desktop=row.notify_desktop,
        )
