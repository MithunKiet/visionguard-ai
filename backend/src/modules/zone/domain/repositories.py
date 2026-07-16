from __future__ import annotations

from abc import ABC, abstractmethod

from src.modules.zone.domain.entities import ZoneEntity
from src.shared.security.scope import ScopeFilter


class IZoneRepository(ABC):

    @abstractmethod
    async def get_by_id(
        self, zone_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> ZoneEntity | None: ...

    @abstractmethod
    async def create(self, entity: ZoneEntity) -> ZoneEntity: ...

    @abstractmethod
    async def update(self, entity: ZoneEntity) -> ZoneEntity: ...

    @abstractmethod
    async def delete(self, zone_id: str, enterprise_id: str) -> None: ...
