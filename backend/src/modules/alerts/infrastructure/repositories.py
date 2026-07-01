import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.alerts.domain.entities import AlertEntity
from src.shared.database.models import Alert, AlertHistory


class AlertRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, entity: AlertEntity) -> AlertEntity:
        row = Alert(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            factory_id=entity.factory_id,
            department_id=entity.department_id,
            zone_id=entity.zone_id,
            camera_id=entity.camera_id,
            violation_id=entity.violation_id,
            alert_number=entity.alert_number,
            alert_type=entity.alert_type,
            severity=entity.severity,
            status="Open",
            shift_id=entity.shift_id,
            sla_due_at=entity.sla_due_at,
            created_by=entity.created_by,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def get_by_id(self, alert_id: UUID, enterprise_id: UUID) -> AlertEntity | None:
        result = await self._db.execute(
            select(Alert).where(
                Alert.id == alert_id,
                Alert.enterprise_id == enterprise_id,
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list(
        self,
        enterprise_id: UUID,
        status: str | None = None,
        severity: str | None = None,
        zone_id: UUID | None = None,
        assigned_to: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AlertEntity], int]:
        q = select(Alert).where(Alert.enterprise_id == enterprise_id)
        if status:
            q = q.where(Alert.status == status)
        if severity:
            q = q.where(Alert.severity == severity)
        if zone_id:
            q = q.where(Alert.zone_id == zone_id)
        if assigned_to:
            q = q.where(Alert.assigned_to == assigned_to)

        total = (await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        q = q.order_by(Alert.created_on.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(q)).scalars()
        return [self._to_entity(r) for r in rows], total

    async def exists_open(self, zone_id: UUID, camera_id: UUID, alert_type: str, cooldown_seconds: int) -> bool:
        """Deduplication — true if same alert created within cooldown window."""
        from sqlalchemy import text
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
        result = await self._db.execute(
            select(func.count()).where(
                Alert.zone_id == zone_id,
                Alert.camera_id == camera_id,
                Alert.alert_type == alert_type,
                Alert.status.in_(["Open", "Acknowledged"]),
                Alert.created_on >= cutoff,
            )
        )
        return result.scalar_one() > 0

    async def transition(
        self,
        alert_id: UUID,
        enterprise_id: UUID,
        to_status: str,
        changed_by: UUID | None,
        comment: str | None = None,
    ) -> AlertEntity:
        alert = await self.get_by_id(alert_id, enterprise_id)
        now = datetime.now(timezone.utc)
        values: dict = {"status": to_status}

        if to_status == "Acknowledged":
            values["acknowledged_on"] = now
        elif to_status in ("Resolved", "FalsePositive"):
            values["resolved_on"] = now

        await self._db.execute(
            update(Alert).where(Alert.id == alert_id).values(**values)
        )
        # Append history
        self._db.add(AlertHistory(
            id=uuid.uuid4(),
            alert_id=alert_id,
            from_status=alert.status,
            to_status=to_status,
            changed_by=changed_by,
            changed_at=now,
            comment=comment,
        ))
        await self._db.commit()
        alert.status = to_status
        return alert

    async def assign(self, alert_id: UUID, enterprise_id: UUID, user_id: UUID) -> None:
        await self._db.execute(
            update(Alert)
            .where(Alert.id == alert_id, Alert.enterprise_id == enterprise_id)
            .values(assigned_to=user_id)
        )
        await self._db.commit()

    async def next_sequence(self, enterprise_id: UUID) -> int:
        result = await self._db.execute(
            select(func.count()).where(Alert.enterprise_id == enterprise_id)
        )
        return result.scalar_one() + 1

    @staticmethod
    def _to_entity(row: Alert) -> AlertEntity:
        return AlertEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            factory_id=row.factory_id,
            department_id=row.department_id,
            zone_id=row.zone_id,
            camera_id=row.camera_id,
            violation_id=row.violation_id,
            alert_number=row.alert_number,
            alert_type=row.alert_type,
            severity=row.severity,
            status=row.status,
            assigned_to=row.assigned_to,
            shift_id=row.shift_id,
            sla_due_at=row.sla_due_at,
            created_on=row.created_on,
            acknowledged_on=row.acknowledged_on,
            resolved_on=row.resolved_on,
            created_by=row.created_by,
        )
