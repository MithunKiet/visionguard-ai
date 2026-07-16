from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.occupancy.domain.entities import OccupancyLogEntity
from src.shared.database.models import Camera, Enterprise, OccupancyLog, Shift, Zone
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_zone_scope


class OccupancyRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, entity: OccupancyLogEntity) -> OccupancyLogEntity:
        row = OccupancyLog(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            zone_id=await to_pk(self._db, Zone, entity.zone_id),
            camera_id=await to_pk(self._db, Camera, entity.camera_id),
            current_count=entity.current_count,
            shift_id=await to_pk(self._db, Shift, entity.shift_id),
            timestamp=entity.timestamp,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        entity.id = row.public_id
        return entity

    async def current_per_zone(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[dict]:
        """Latest occupancy reading per zone with zone name + capacity."""
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        latest_ts = (
            select(
                OccupancyLog.zone_id.label("zone_id"),
                func.max(OccupancyLog.timestamp).label("max_ts"),
            )
            .where(OccupancyLog.enterprise_id == ent_pk)
            .group_by(OccupancyLog.zone_id)
            .subquery()
        )
        q = (
            select(OccupancyLog, Zone.name, Zone.public_id, Zone.max_occupancy, Camera.public_id)
            .join(
                latest_ts,
                (OccupancyLog.zone_id == latest_ts.c.zone_id)
                & (OccupancyLog.timestamp == latest_ts.c.max_ts),
            )
            .join(Zone, Zone.id == OccupancyLog.zone_id)
            .join(Camera, Camera.id == OccupancyLog.camera_id)
        )
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Zone.factory_id, OccupancyLog.zone_id)
        rows = (await self._db.execute(q)).all()
        return [
            {
                "zone_id": zone_public_id,
                "zone_name": zone_name,
                "camera_id": camera_public_id,
                "current_count": log.current_count,
                "max_occupancy": max_occupancy,
                "over_capacity": max_occupancy is not None and log.current_count > max_occupancy,
                "timestamp": log.timestamp.isoformat(),
            }
            for log, zone_name, zone_public_id, max_occupancy, camera_public_id in rows
        ]

    async def history(
        self,
        enterprise_id: str,
        zone_id: str | None,
        from_dt: datetime | None,
        to_dt: datetime | None,
        page: int,
        page_size: int,
        scope: ScopeFilter | None = None,
    ) -> tuple[list[OccupancyLogEntity], int]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(OccupancyLog).where(OccupancyLog.enterprise_id == ent_pk)
        if zone_id:
            q = q.where(OccupancyLog.zone_id == await to_pk(self._db, Zone, zone_id))
        if from_dt:
            q = q.where(OccupancyLog.timestamp >= from_dt)
        if to_dt:
            q = q.where(OccupancyLog.timestamp <= to_dt)
        if scope is not None:
            # OccupancyLog has no factory_id of its own — join Zone to get one.
            q = q.join(Zone, Zone.id == OccupancyLog.zone_id)
            q = await apply_zone_scope(self._db, q, scope, Zone.factory_id, OccupancyLog.zone_id)

        total = (await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        q = q.order_by(OccupancyLog.timestamp.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(q)).scalars()
        return [await self._to_entity(r) for r in rows], total

    async def _to_entity(self, row: OccupancyLog) -> OccupancyLogEntity:
        return OccupancyLogEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            zone_id=await to_public_id(self._db, Zone, row.zone_id),
            camera_id=await to_public_id(self._db, Camera, row.camera_id),
            current_count=row.current_count,
            shift_id=await to_public_id(self._db, Shift, row.shift_id),
            timestamp=row.timestamp,
        )
