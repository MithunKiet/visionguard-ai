from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.alerts.domain.entities import AlertEntity
from src.shared.database.models import (
    Alert,
    AlertHistory,
    Camera,
    Department,
    Enterprise,
    Factory,
    PPEViolation,
    Shift,
    User,
    Zone,
)
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_zone_scope

# Alert has 8 FK-shaped fields; resolving each with a separate to_public_id
# query per row is an N+1 query storm on list() (a 20-row page = ~160 round
# trips). Join every referenced table once instead and read public_id
# straight off the joined row — see _to_entity_from_row. Factory/Zone/Camera
# are NOT NULL on Alert so inner joins are safe; the rest are nullable.
_JOINED_COLUMNS = (
    Alert, Factory.public_id, Department.public_id, Zone.public_id,
    Camera.public_id, PPEViolation.public_id, User.public_id, Shift.public_id,
)


class AlertRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, entity: AlertEntity) -> AlertEntity:
        row = Alert(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            factory_id=await to_pk(self._db, Factory, entity.factory_id),
            department_id=await to_pk(self._db, Department, entity.department_id),
            zone_id=await to_pk(self._db, Zone, entity.zone_id),
            camera_id=await to_pk(self._db, Camera, entity.camera_id),
            violation_id=await to_pk(self._db, PPEViolation, entity.violation_id),
            alert_number=entity.alert_number,
            alert_type=entity.alert_type,
            severity=entity.severity,
            status="Open",
            shift_id=await to_pk(self._db, Shift, entity.shift_id),
            sla_due_at=entity.sla_due_at,
            created_source=entity.created_by,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return await self._to_entity(row)

    async def get_by_id(
        self, alert_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> AlertEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(Alert).where(
            Alert.public_id == alert_id,
            Alert.enterprise_id == ent_pk,
        )
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Alert.factory_id, Alert.zone_id)
        result = await self._db.execute(q)
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def list(
        self,
        enterprise_id: str,
        status: str | None = None,
        severity: str | None = None,
        zone_id: str | None = None,
        assigned_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
        scope: ScopeFilter | None = None,
    ) -> tuple[list[AlertEntity], int]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(*_JOINED_COLUMNS)
            .join(Factory, Factory.id == Alert.factory_id)
            .join(Zone, Zone.id == Alert.zone_id)
            .join(Camera, Camera.id == Alert.camera_id)
            .outerjoin(Department, Department.id == Alert.department_id)
            .outerjoin(PPEViolation, PPEViolation.id == Alert.violation_id)
            .outerjoin(User, User.id == Alert.assigned_to)
            .outerjoin(Shift, Shift.id == Alert.shift_id)
            .where(Alert.enterprise_id == ent_pk)
        )
        if status:
            q = q.where(Alert.status == status)
        if severity:
            q = q.where(Alert.severity == severity)
        if zone_id:
            q = q.where(Alert.zone_id == await to_pk(self._db, Zone, zone_id))
        if assigned_to:
            q = q.where(Alert.assigned_to == await to_pk(self._db, User, assigned_to))
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Alert.factory_id, Alert.zone_id)

        total = (await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        q = q.order_by(Alert.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(q)).all()
        return [self._to_entity_from_row(*row, enterprise_id) for row in rows], total

    async def exists_open(self, zone_id: str, camera_id: str, alert_type: str, cooldown_seconds: int) -> bool:
        """Deduplication — true if same alert created within cooldown window."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
        zone_pk = await to_pk(self._db, Zone, zone_id)
        camera_pk = await to_pk(self._db, Camera, camera_id)
        result = await self._db.execute(
            select(func.count()).where(
                Alert.zone_id == zone_pk,
                Alert.camera_id == camera_pk,
                Alert.alert_type == alert_type,
                Alert.status.in_(["Open", "Acknowledged"]),
                Alert.created_at >= cutoff,
            )
        )
        return result.scalar_one() > 0

    async def transition(
        self,
        alert_id: str,
        enterprise_id: str,
        to_status: str,
        changed_by: str | None,
        comment: str | None = None,
        scope: ScopeFilter | None = None,
    ) -> AlertEntity:
        alert = await self.get_by_id(alert_id, enterprise_id, scope)
        now = datetime.now(timezone.utc)
        values: dict = {"status": to_status}

        if to_status == "Acknowledged":
            values["acknowledged_on"] = now
        elif to_status in ("Resolved", "FalsePositive"):
            values["resolved_on"] = now

        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(Alert).where(Alert.public_id == alert_id, Alert.enterprise_id == ent_pk).values(**values)
        )
        alert_pk = await to_pk(self._db, Alert, alert_id)
        # Append history
        self._db.add(AlertHistory(
            alert_id=alert_pk,
            from_status=alert.status,
            to_status=to_status,
            created_by=str(changed_by) if changed_by else None,
            created_at=now,
            comment=comment,
        ))
        await self._db.commit()
        alert.status = to_status
        return alert

    async def assign(self, alert_id: str, enterprise_id: str, user_id: str) -> None:
        # The caller (AlertService.assign) already verified via a scoped
        # get_by_id that this alert is visible before calling this — the
        # public_id/enterprise_id match here is what it actually needs
        # (the row was already confirmed to exist and be in scope).
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        user_pk = await to_pk(self._db, User, user_id)
        await self._db.execute(
            update(Alert)
            .where(Alert.public_id == alert_id, Alert.enterprise_id == ent_pk)
            .values(assigned_to=user_pk)
        )
        await self._db.commit()

    async def next_sequence(self, enterprise_id: str) -> int:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        result = await self._db.execute(
            select(func.count()).where(Alert.enterprise_id == ent_pk)
        )
        return result.scalar_one() + 1

    async def _to_entity(self, row: Alert) -> AlertEntity:
        """Single-row path (create/get_by_id/transition) — not a hot list
        endpoint, so the per-field resolves here are an acceptable one-off
        cost. list() below uses a joined query instead — see _JOINED_COLUMNS."""
        return AlertEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            factory_id=await to_public_id(self._db, Factory, row.factory_id),
            department_id=await to_public_id(self._db, Department, row.department_id),
            zone_id=await to_public_id(self._db, Zone, row.zone_id),
            camera_id=await to_public_id(self._db, Camera, row.camera_id),
            violation_id=await to_public_id(self._db, PPEViolation, row.violation_id),
            alert_number=row.alert_number,
            alert_type=row.alert_type,
            severity=row.severity,
            status=row.status,
            assigned_to=await to_public_id(self._db, User, row.assigned_to),
            shift_id=await to_public_id(self._db, Shift, row.shift_id),
            sla_due_at=row.sla_due_at,
            created_at=row.created_at,
            acknowledged_on=row.acknowledged_on,
            resolved_on=row.resolved_on,
            created_by=row.created_source,
        )

    @staticmethod
    def _to_entity_from_row(
        a: Alert, factory_public_id: str, department_public_id: str | None,
        zone_public_id: str, camera_public_id: str, violation_public_id: str | None,
        assigned_to_public_id: str | None, shift_public_id: str | None,
        enterprise_id: str,
    ) -> AlertEntity:
        return AlertEntity(
            id=a.public_id,
            enterprise_id=enterprise_id,
            factory_id=factory_public_id,
            department_id=department_public_id,
            zone_id=zone_public_id,
            camera_id=camera_public_id,
            violation_id=violation_public_id,
            alert_number=a.alert_number,
            alert_type=a.alert_type,
            severity=a.severity,
            status=a.status,
            assigned_to=assigned_to_public_id,
            shift_id=shift_public_id,
            sla_due_at=a.sla_due_at,
            created_at=a.created_at,
            acknowledged_on=a.acknowledged_on,
            resolved_on=a.resolved_on,
            created_by=a.created_source,
        )
