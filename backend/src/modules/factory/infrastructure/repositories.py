from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.factory.domain.entities import FactoryEntity
from src.modules.factory.domain.repositories import IFactoryRepository
from src.shared.database.models import Enterprise, Factory, User
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_factory_scope


class FactoryRepository(IFactoryRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[FactoryEntity]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(Factory)
            .where(Factory.enterprise_id == ent_pk, Factory.deleted_at.is_(None))
            .order_by(Factory.name)
        )
        if scope is not None:
            q = await apply_factory_scope(self._db, q, scope, Factory.id)
        result = await self._db.execute(q)
        return [await self._to_entity(r) for r in result.scalars()]

    async def get_by_id(self, factory_id: str, enterprise_id: str) -> FactoryEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        result = await self._db.execute(
            select(Factory).where(
                Factory.public_id == factory_id,
                Factory.enterprise_id == ent_pk,
                Factory.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def create(self, entity: FactoryEntity) -> FactoryEntity:
        row = Factory(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            name=entity.name,
            code=entity.code,
            location=entity.location,
            plant_head_id=await to_pk(self._db, User, entity.plant_head_id),
            status=entity.status,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return await self._to_entity(row)

    async def update(self, entity: FactoryEntity) -> FactoryEntity:
        await self._db.execute(
            update(Factory).where(Factory.public_id == entity.id).values(
                name=entity.name,
                location=entity.location,
                plant_head_id=await to_pk(self._db, User, entity.plant_head_id),
                status=entity.status,
                updated_at=datetime.now(timezone.utc),
                version=Factory.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, factory_id: str, enterprise_id: str) -> None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(Factory).where(
                Factory.public_id == factory_id,
                Factory.enterprise_id == ent_pk,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def _to_entity(self, row: Factory) -> FactoryEntity:
        return FactoryEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            name=row.name,
            code=row.code,
            status=row.status,
            location=row.location,
            plant_head_id=await to_public_id(self._db, User, row.plant_head_id),
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )
