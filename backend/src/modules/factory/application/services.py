"""
FactoryService — CRUD for the enterprise's factories/plants.
"""
import structlog

from src.core.exceptions import NotFoundException
from src.modules.factory.domain.entities import FactoryEntity
from src.modules.factory.infrastructure.repositories import FactoryRepository
from src.shared.security.scope import ScopeFilter

log = structlog.get_logger()


class FactoryService:

    def __init__(self, repo: FactoryRepository):
        self._repo = repo

    async def list_factories(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[FactoryEntity]:
        return await self._repo.list(enterprise_id, scope)

    async def get_factory(self, factory_id: str, enterprise_id: str) -> FactoryEntity:
        factory = await self._repo.get_by_id(factory_id, enterprise_id)
        if not factory:
            raise NotFoundException("Factory", str(factory_id))
        return factory

    async def create_factory(
        self,
        enterprise_id: str,
        name: str,
        code: str,
        location: str | None = None,
        plant_head_id: str | None = None,
    ) -> FactoryEntity:
        entity = FactoryEntity(
            enterprise_id=enterprise_id,
            name=name,
            code=code,
            location=location,
            plant_head_id=plant_head_id,
        )
        factory = await self._repo.create(entity)
        log.info("factory.created", factory_id=str(factory.id), name=name)
        return factory

    async def update_factory(self, factory_id: str, enterprise_id: str, **fields) -> FactoryEntity:
        factory = await self.get_factory(factory_id, enterprise_id)
        for key, val in fields.items():
            if val is not None and hasattr(factory, key):
                setattr(factory, key, val)
        return await self._repo.update(factory)

    async def delete_factory(self, factory_id: str, enterprise_id: str) -> None:
        await self.get_factory(factory_id, enterprise_id)
        await self._repo.delete(factory_id, enterprise_id)
        log.info("factory.deleted", factory_id=str(factory_id))

    @staticmethod
    def to_dict(f: FactoryEntity) -> dict:
        return {
            "id": f.id,
            "enterprise_id": f.enterprise_id,
            "name": f.name,
            "code": f.code,
            "location": f.location,
            "plant_head_id": f.plant_head_id,
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        }
