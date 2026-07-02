from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.occupancy.domain.entities import OccupancyLogEntity
from src.shared.database.models import OccupancyLog, Zone


class OccupancyRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, entity: OccupancyLogEntity) -> OccupancyLogEntity:
        row = OccupancyLog(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            zone_id=entity.zone_id,
            camera_id=entity.camera_id,
            current_count=entity.current_count,
            shift_id=entity.shift_id,
            timestamp=entity.timestamp,
        )
        self._db.add(row)
        await self._db.commit()
        return entity

    async def current_per_zone(self, enterprise_id: UUID) -> list[dict]:
        """Latest occupancy reading per zone with zone name + capacity."""
        latest_ts = (
            select(
                OccupancyLog.zone_id.label("zone_id"),
                func.max(OccupancyLog.timestamp).label("max_ts"),
            )
            .where(OccupancyLog.enterprise_id == enterprise_id)
            .group_by(OccupancyLog.zone_id)
            .subquery()
        )
        q = (
            select(OccupancyLog, Zone.name, Zone.max_occupancy)
            .join(
                latest_ts,
                (OccupancyLog.zone_id == latest_ts.c.zone_id)
                & (OccupancyLog.timestamp == latest_ts.c.max_ts),
            )
            .join(Zone, Zone.id == OccupancyLog.zone_id)
        )
        rows = (await self._db.execute(q)).all()
        return [
            {
                "zone_id": str(log.zone_id),
                "zone_name": zone_name,
                "camera_id": str(log.camera_id),
                "current_count": log.current_count,
                "max_occupancy": max_occupancy,
                "over_capacity": max_occupancy is not None and log.current_count > max_occupancy,
                "timestamp": log.timestamp.isoformat(),
            }
            for log, zone_name, max_occupancy in rows
        ]

    async def history(
        self,
        enterprise_id: UUID,
        zone_id: UUID | None,
        from_dt: datetime | None,
        to_dt: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[OccupancyLogEntity], int]:
        q = select(OccupancyLog).where(OccupancyLog.enterprise_id == enterprise_id)
        if zone_id:
            q = q.where(OccupancyLog.zone_id == zone_id)
        if from_dt:
            q = q.where(OccupancyLog.timestamp >= from_dt)
        if to_dt:
            q = q.where(OccupancyLog.timestamp <= to_dt)

        total = (await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        q = q.order_by(OccupancyLog.timestamp.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(q)).scalars()
        return [self._to_entity(r) for r in rows], total

    @staticmethod
    def _to_entity(row: OccupancyLog) -> OccupancyLogEntity:
        return OccupancyLogEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            zone_id=row.zone_id,
            camera_id=row.camera_id,
            current_count=row.current_count,
            shift_id=row.shift_id,
            timestamp=row.timestamp,
        )
