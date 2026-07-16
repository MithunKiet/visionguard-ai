from __future__ import annotations

from abc import ABC, abstractmethod

from src.modules.factory.domain.entities import FactoryEntity
from src.shared.security.scope import ScopeFilter


class IFactoryRepository(ABC):

    @abstractmethod
    async def list(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[FactoryEntity]: ...

    @abstractmethod
    async def get_by_id(self, factory_id: str, enterprise_id: str) -> FactoryEntity | None: ...

    @abstractmethod
    async def create(self, entity: FactoryEntity) -> FactoryEntity: ...

    @abstractmethod
    async def update(self, entity: FactoryEntity) -> FactoryEntity: ...

    @abstractmethod
    async def delete(self, factory_id: str, enterprise_id: str) -> None: ...
