from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.domain.entities import NotificationRecipientEntity
from src.shared.database.models import Alert, Enterprise, NotificationLog, NotificationRecipient, User, Zone
from src.shared.database.pid import to_pk, to_public_id


class NotificationRecipientRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(self, enterprise_id: str, zone_id: str | None = None) -> list[NotificationRecipientEntity]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(NotificationRecipient).where(NotificationRecipient.enterprise_id == ent_pk)
        if zone_id:
            q = q.where(NotificationRecipient.zone_id == await to_pk(self._db, Zone, zone_id))
        result = await self._db.execute(q.order_by(NotificationRecipient.level))
        return [await self._to_entity(r) for r in result.scalars()]

    async def list_for_zone_with_fallback(self, enterprise_id: str, zone_id: str) -> list[NotificationRecipientEntity]:
        """Zone-specific recipients if any exist, else enterprise-wide (zone_id IS NULL) ones."""
        zone_recipients = await self.list(enterprise_id, zone_id)
        if zone_recipients:
            return zone_recipients

        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        result = await self._db.execute(
            select(NotificationRecipient).where(
                NotificationRecipient.enterprise_id == ent_pk,
                NotificationRecipient.zone_id.is_(None),
            ).order_by(NotificationRecipient.level)
        )
        return [await self._to_entity(r) for r in result.scalars()]

    async def create(self, entity: NotificationRecipientEntity) -> NotificationRecipientEntity:
        row = NotificationRecipient(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            zone_id=await to_pk(self._db, Zone, entity.zone_id),
            user_id=await to_pk(self._db, User, entity.user_id),
            level=entity.level,
            notify_email=entity.notify_email,
            notify_desktop=entity.notify_desktop,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return await self._to_entity(row)

    async def delete(self, recipient_id: str, enterprise_id: str) -> None:
        from sqlalchemy import delete
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            delete(NotificationRecipient).where(
                NotificationRecipient.public_id == recipient_id,
                NotificationRecipient.enterprise_id == ent_pk,
            )
        )
        await self._db.commit()

    async def log_delivery(
        self,
        enterprise_id: str,
        alert_id: str,
        recipient_id: str | None,
        channel: str,
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        self._db.add(NotificationLog(
            enterprise_id=await to_pk(self._db, Enterprise, enterprise_id),
            alert_id=await to_pk(self._db, Alert, alert_id),
            channel=channel,
            recipient_id=await to_pk(self._db, User, recipient_id),
            sent_at=datetime.now(timezone.utc),
            status=status,
            failure_reason=failure_reason,
        ))
        await self._db.commit()

    async def _to_entity(self, row: NotificationRecipient) -> NotificationRecipientEntity:
        return NotificationRecipientEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            zone_id=await to_public_id(self._db, Zone, row.zone_id),
            user_id=await to_public_id(self._db, User, row.user_id),
            level=row.level,
            notify_email=row.notify_email,
            notify_desktop=row.notify_desktop,
        )
