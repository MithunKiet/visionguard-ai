from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.factory.domain.entities import FactoryEntity
from src.modules.factory.domain.repositories import IFactoryRepository
from src.shared.database.models import Factory


class FactoryRepository(IFactoryRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(self, enterprise_id: UUID) -> list[FactoryEntity]:
        result = await self._db.execute(
            select(Factory)
            .where(Factory.enterprise_id == enterprise_id, Factory.deleted_at.is_(None))
            .order_by(Factory.name)
        )
        return [self._to_entity(r) for r in result.scalars()]

    async def get_by_id(self, factory_id: UUID, enterprise_id: UUID) -> FactoryEntity | None:
        result = await self._db.execute(
            select(Factory).where(
                Factory.id == factory_id,
                Factory.enterprise_id == enterprise_id,
                Factory.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def create(self, entity: FactoryEntity) -> FactoryEntity:
        row = Factory(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            name=entity.name,
            code=entity.code,
            location=entity.location,
            plant_head_id=entity.plant_head_id,
            status=entity.status,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def update(self, entity: FactoryEntity) -> FactoryEntity:
        await self._db.execute(
            update(Factory).where(Factory.id == entity.id).values(
                name=entity.name,
                location=entity.location,
                plant_head_id=entity.plant_head_id,
                status=entity.status,
                modified_on=datetime.now(timezone.utc),
                version=Factory.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, factory_id: UUID, enterprise_id: UUID) -> None:
        await self._db.execute(
            update(Factory).where(
                Factory.id == factory_id,
                Factory.enterprise_id == enterprise_id,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    @staticmethod
    def _to_entity(row: Factory) -> FactoryEntity:
        return FactoryEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            name=row.name,
            code=row.code,
            status=row.status,
            location=row.location,
            plant_head_id=row.plant_head_id,
            created_on=row.created_on,
            modified_on=row.modified_on,
            deleted_at=row.deleted_at,
        )
