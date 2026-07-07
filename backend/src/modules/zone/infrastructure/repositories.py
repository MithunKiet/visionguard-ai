from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.zone.domain.entities import ZoneEntity
from src.modules.zone.domain.repositories import IZoneRepository
from src.shared.database.models import Zone


class ZoneRepository(IZoneRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(self, zone_id: UUID, enterprise_id: UUID) -> ZoneEntity | None:
        result = await self._db.execute(
            select(Zone).where(
                Zone.id == zone_id,
                Zone.enterprise_id == enterprise_id,
                Zone.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def create(self, entity: ZoneEntity) -> ZoneEntity:
        row = Zone(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            factory_id=entity.factory_id,
            department_id=entity.department_id,
            name=entity.name,
            code=entity.code,
            max_occupancy=entity.max_occupancy,
            supervisor_id=entity.supervisor_id,
            zone_type=entity.zone_type,
            is_restricted=entity.is_restricted,
            status=entity.status,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def update(self, entity: ZoneEntity) -> ZoneEntity:
        await self._db.execute(
            update(Zone).where(Zone.id == entity.id).values(
                name=entity.name,
                max_occupancy=entity.max_occupancy,
                supervisor_id=entity.supervisor_id,
                zone_type=entity.zone_type,
                is_restricted=entity.is_restricted,
                status=entity.status,
                modified_on=datetime.now(timezone.utc),
                version=Zone.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, zone_id: UUID, enterprise_id: UUID) -> None:
        await self._db.execute(
            update(Zone).where(
                Zone.id == zone_id,
                Zone.enterprise_id == enterprise_id,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    @staticmethod
    def _to_entity(row: Zone) -> ZoneEntity:
        return ZoneEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            factory_id=row.factory_id,
            department_id=row.department_id,
            name=row.name,
            code=row.code,
            max_occupancy=row.max_occupancy,
            status=row.status,
            zone_type=row.zone_type,
            is_restricted=row.is_restricted,
            supervisor_id=row.supervisor_id,
            created_on=row.created_on,
            modified_on=row.modified_on,
            deleted_at=row.deleted_at,
        )
