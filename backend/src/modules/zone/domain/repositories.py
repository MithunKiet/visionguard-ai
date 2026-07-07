from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.modules.zone.domain.entities import ZoneEntity


class IZoneRepository(ABC):

    @abstractmethod
    async def get_by_id(self, zone_id: UUID, enterprise_id: UUID) -> ZoneEntity | None: ...

    @abstractmethod
    async def create(self, entity: ZoneEntity) -> ZoneEntity: ...

    @abstractmethod
    async def update(self, entity: ZoneEntity) -> ZoneEntity: ...

    @abstractmethod
    async def delete(self, zone_id: UUID, enterprise_id: UUID) -> None: ...
