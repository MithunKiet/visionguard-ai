from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.ppe.domain.entities import ViolationEntity
from src.shared.database.models import PPEViolation


class ViolationRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, entity: ViolationEntity) -> ViolationEntity:
        row = PPEViolation(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            zone_id=entity.zone_id,
            camera_id=entity.camera_id,
            violation_type=entity.violation_type,
            confidence=entity.confidence,
            snapshot_key=entity.snapshot_key,
            track_id=entity.track_id,
            shift_id=entity.shift_id,
            rule_id=entity.rule_id,
            is_false_positive=False,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def get_by_id(self, violation_id: UUID, enterprise_id: UUID) -> ViolationEntity | None:
        result = await self._db.execute(
            select(PPEViolation).where(
                PPEViolation.id == violation_id,
                PPEViolation.enterprise_id == enterprise_id,
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list(
        self,
        enterprise_id: UUID,
        zone_id: UUID | None = None,
        camera_id: UUID | None = None,
        violation_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        needs_review: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ViolationEntity], int]:
        q = select(PPEViolation).where(PPEViolation.enterprise_id == enterprise_id)
        if zone_id:
            q = q.where(PPEViolation.zone_id == zone_id)
        if camera_id:
            q = q.where(PPEViolation.camera_id == camera_id)
        if violation_type:
            q = q.where(PPEViolation.violation_type == violation_type)
        if from_dt:
            q = q.where(PPEViolation.created_on >= from_dt)
        if to_dt:
            q = q.where(PPEViolation.created_on <= to_dt)

        total_result = await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = total_result.scalar_one()

        q = q.order_by(PPEViolation.created_on.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self._db.execute(q)
        items = [self._to_entity(r) for r in result.scalars()]
        return items, total

    async def mark_false_positive(
        self, violation_id: UUID, enterprise_id: UUID, reason: str
    ) -> None:
        await self._db.execute(
            update(PPEViolation)
            .where(
                PPEViolation.id == violation_id,
                PPEViolation.enterprise_id == enterprise_id,
            )
            .values(is_false_positive=True, fp_reason=reason)
        )
        await self._db.commit()

    @staticmethod
    def _to_entity(row: PPEViolation) -> ViolationEntity:
        return ViolationEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            zone_id=row.zone_id,
            camera_id=row.camera_id,
            violation_type=row.violation_type,
            confidence=row.confidence,
            snapshot_key=row.snapshot_key,
            track_id=row.track_id,
            shift_id=row.shift_id,
            rule_id=row.rule_id,
            is_false_positive=row.is_false_positive,
            fp_reason=row.fp_reason,
            needs_review=row.confidence < 0.60,
            created_on=row.created_on,
        )
