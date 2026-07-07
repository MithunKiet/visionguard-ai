"""
FactoryService — CRUD for the enterprise's factories/plants.
"""
import uuid
from uuid import UUID

import structlog

from src.core.exceptions import NotFoundException
from src.modules.factory.domain.entities import FactoryEntity
from src.modules.factory.infrastructure.repositories import FactoryRepository

log = structlog.get_logger()


class FactoryService:

    def __init__(self, repo: FactoryRepository):
        self._repo = repo

    async def list_factories(self, enterprise_id: UUID) -> list[FactoryEntity]:
        return await self._repo.list(enterprise_id)

    async def get_factory(self, factory_id: UUID, enterprise_id: UUID) -> FactoryEntity:
        factory = await self._repo.get_by_id(factory_id, enterprise_id)
        if not factory:
            raise NotFoundException("Factory", str(factory_id))
        return factory

    async def create_factory(
        self,
        enterprise_id: UUID,
        name: str,
        code: str,
        location: str | None = None,
        plant_head_id: UUID | None = None,
    ) -> FactoryEntity:
        entity = FactoryEntity(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            name=name,
            code=code,
            location=location,
            plant_head_id=plant_head_id,
        )
        factory = await self._repo.create(entity)
        log.info("factory.created", factory_id=str(factory.id), name=name)
        return factory

    async def update_factory(self, factory_id: UUID, enterprise_id: UUID, **fields) -> FactoryEntity:
        factory = await self.get_factory(factory_id, enterprise_id)
        for key, val in fields.items():
            if val is not None and hasattr(factory, key):
                setattr(factory, key, val)
        return await self._repo.update(factory)

    async def delete_factory(self, factory_id: UUID, enterprise_id: UUID) -> None:
        await self.get_factory(factory_id, enterprise_id)
        await self._repo.delete(factory_id, enterprise_id)
        log.info("factory.deleted", factory_id=str(factory_id))

    @staticmethod
    def to_dict(f: FactoryEntity) -> dict:
        return {
            "id": str(f.id),
            "enterprise_id": str(f.enterprise_id),
            "name": f.name,
            "code": f.code,
            "location": f.location,
            "plant_head_id": str(f.plant_head_id) if f.plant_head_id else None,
            "status": f.status,
            "created_on": f.created_on.isoformat() if f.created_on else None,
            "modified_on": f.modified_on.isoformat() if f.modified_on else None,
        }
