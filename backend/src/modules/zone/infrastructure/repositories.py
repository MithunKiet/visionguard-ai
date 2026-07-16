from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.zone.domain.entities import ZoneEntity
from src.modules.zone.domain.repositories import IZoneRepository
from src.shared.database.models import Department, Enterprise, Factory, User, Zone
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_zone_scope


class ZoneRepository(IZoneRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_id(
        self, zone_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> ZoneEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(Zone).where(
            Zone.public_id == zone_id,
            Zone.enterprise_id == ent_pk,
            Zone.deleted_at.is_(None),
        )
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Zone.factory_id, Zone.id)
        result = await self._db.execute(q)
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def create(self, entity: ZoneEntity) -> ZoneEntity:
        row = Zone(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            factory_id=await to_pk(self._db, Factory, entity.factory_id),
            department_id=await to_pk(self._db, Department, entity.department_id),
            name=entity.name,
            code=entity.code,
            max_occupancy=entity.max_occupancy,
            supervisor_id=await to_pk(self._db, User, entity.supervisor_id),
            zone_type=entity.zone_type,
            is_restricted=entity.is_restricted,
            status=entity.status,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return await self._to_entity(row)

    async def update(self, entity: ZoneEntity) -> ZoneEntity:
        await self._db.execute(
            update(Zone).where(Zone.public_id == entity.id).values(
                name=entity.name,
                max_occupancy=entity.max_occupancy,
                supervisor_id=await to_pk(self._db, User, entity.supervisor_id),
                zone_type=entity.zone_type,
                is_restricted=entity.is_restricted,
                status=entity.status,
                updated_at=datetime.now(timezone.utc),
                version=Zone.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, zone_id: str, enterprise_id: str) -> None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(Zone).where(
                Zone.public_id == zone_id,
                Zone.enterprise_id == ent_pk,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def _to_entity(self, row: Zone) -> ZoneEntity:
        return ZoneEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            factory_id=await to_public_id(self._db, Factory, row.factory_id),
            department_id=await to_public_id(self._db, Department, row.department_id),
            name=row.name,
            code=row.code,
            max_occupancy=row.max_occupancy,
            status=row.status,
            zone_type=row.zone_type,
            is_restricted=row.is_restricted,
            supervisor_id=await to_public_id(self._db, User, row.supervisor_id),
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )
