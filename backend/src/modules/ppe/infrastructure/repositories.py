from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ppe.domain.entities import ViolationEntity
from src.shared.database.models import Camera, Enterprise, PPEViolation, Shift, Zone, ZoneRule
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_zone_scope

# Columns pulled alongside PPEViolation in the list/get joins below so
# building a ViolationEntity needs zero additional per-row queries — see
# _to_entity_from_row. Left joins on Shift/ZoneRule since both are nullable.
_JOINED_COLUMNS = (
    PPEViolation, Zone.name, Zone.public_id, Camera.name, Camera.code,
    Camera.public_id, Shift.public_id, ZoneRule.public_id,
)


class ViolationRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, entity: ViolationEntity) -> ViolationEntity:
        zone_pk = await to_pk(self._db, Zone, entity.zone_id)
        camera_pk = await to_pk(self._db, Camera, entity.camera_id)
        row = PPEViolation(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            zone_id=zone_pk,
            camera_id=camera_pk,
            violation_type=entity.violation_type,
            confidence=entity.confidence,
            snapshot_key=entity.snapshot_key,
            track_id=entity.track_id,
            shift_id=await to_pk(self._db, Shift, entity.shift_id),
            rule_id=await to_pk(self._db, ZoneRule, entity.rule_id),
            is_false_positive=False,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)

        # A single freshly-created row — one-off lookups here are fine
        # (this is the write path, not the hot list/get read path the
        # _JOINED_COLUMNS query above exists to keep query-count-free).
        zone_name = await self._db.scalar(select(Zone.name).where(Zone.id == zone_pk))
        camera_name, camera_code = (await self._db.execute(
            select(Camera.name, Camera.code).where(Camera.id == camera_pk)
        )).one()

        return ViolationEntity(
            id=row.public_id,
            enterprise_id=entity.enterprise_id,
            zone_id=entity.zone_id,
            camera_id=entity.camera_id,
            violation_type=row.violation_type,
            confidence=row.confidence,
            snapshot_key=row.snapshot_key,
            track_id=row.track_id,
            shift_id=await to_public_id(self._db, Shift, row.shift_id),
            rule_id=await to_public_id(self._db, ZoneRule, row.rule_id),
            is_false_positive=row.is_false_positive,
            fp_reason=row.fp_reason,
            needs_review=row.confidence < 0.60,
            created_at=row.created_at,
            zone_name=zone_name,
            camera_name=camera_name,
            camera_code=camera_code,
        )

    async def get_by_id(
        self, violation_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> ViolationEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(*_JOINED_COLUMNS)
            .join(Zone, Zone.id == PPEViolation.zone_id)
            .join(Camera, Camera.id == PPEViolation.camera_id)
            .outerjoin(Shift, Shift.id == PPEViolation.shift_id)
            .outerjoin(ZoneRule, ZoneRule.id == PPEViolation.rule_id)
            .where(
                PPEViolation.public_id == violation_id,
                PPEViolation.enterprise_id == ent_pk,
            )
        )
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Zone.factory_id, PPEViolation.zone_id)
        row = (await self._db.execute(q)).first()
        return self._to_entity_from_row(*row, enterprise_id) if row else None

    async def list(
        self,
        enterprise_id: str,
        zone_id: str | None = None,
        camera_id: str | None = None,
        violation_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        needs_review: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        scope: ScopeFilter | None = None,
    ) -> tuple[list[ViolationEntity], int]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(*_JOINED_COLUMNS)
            .join(Zone, Zone.id == PPEViolation.zone_id)
            .join(Camera, Camera.id == PPEViolation.camera_id)
            .outerjoin(Shift, Shift.id == PPEViolation.shift_id)
            .outerjoin(ZoneRule, ZoneRule.id == PPEViolation.rule_id)
            .where(PPEViolation.enterprise_id == ent_pk)
        )
        if zone_id:
            q = q.where(PPEViolation.zone_id == await to_pk(self._db, Zone, zone_id))
        if camera_id:
            q = q.where(PPEViolation.camera_id == await to_pk(self._db, Camera, camera_id))
        if violation_type:
            q = q.where(PPEViolation.violation_type == violation_type)
        if from_dt:
            q = q.where(PPEViolation.created_at >= from_dt)
        if to_dt:
            q = q.where(PPEViolation.created_at <= to_dt)
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Zone.factory_id, PPEViolation.zone_id)

        total_result = await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = total_result.scalar_one()

        q = q.order_by(PPEViolation.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(q)).all()
        items = [self._to_entity_from_row(*row, enterprise_id) for row in rows]
        return items, total

    async def mark_false_positive(
        self, violation_id: str, enterprise_id: str, reason: str
    ) -> None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(PPEViolation)
            .where(
                PPEViolation.public_id == violation_id,
                PPEViolation.enterprise_id == ent_pk,
            )
            .values(is_false_positive=True, fp_reason=reason)
        )
        await self._db.commit()

    @staticmethod
    def _to_entity_from_row(
        v: PPEViolation, zone_name: str, zone_public_id: str,
        camera_name: str, camera_code: str, camera_public_id: str,
        shift_public_id: str | None, rule_public_id: str | None,
        enterprise_id: str,
    ) -> ViolationEntity:
        return ViolationEntity(
            id=v.public_id,
            enterprise_id=enterprise_id,
            zone_id=zone_public_id,
            camera_id=camera_public_id,
            violation_type=v.violation_type,
            confidence=v.confidence,
            snapshot_key=v.snapshot_key,
            track_id=v.track_id,
            shift_id=shift_public_id,
            rule_id=rule_public_id,
            is_false_positive=v.is_false_positive,
            fp_reason=v.fp_reason,
            needs_review=v.confidence < 0.60,
            created_at=v.created_at,
            zone_name=zone_name,
            camera_name=camera_name,
            camera_code=camera_code,
        )
