from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.modules.factory.domain.entities import FactoryEntity


class IFactoryRepository(ABC):

    @abstractmethod
    async def list(self, enterprise_id: UUID) -> list[FactoryEntity]: ...

    @abstractmethod
    async def get_by_id(self, factory_id: UUID, enterprise_id: UUID) -> FactoryEntity | None: ...

    @abstractmethod
    async def create(self, entity: FactoryEntity) -> FactoryEntity: ...

    @abstractmethod
    async def update(self, entity: FactoryEntity) -> FactoryEntity: ...

    @abstractmethod
    async def delete(self, factory_id: UUID, enterprise_id: UUID) -> None: ...
