from __future__ import annotations

from abc import ABC, abstractmethod

from src.modules.camera.domain.entities import CameraEntity
from src.shared.security.scope import ScopeFilter


class ICameraRepository(ABC):

    @abstractmethod
    async def list(
        self, enterprise_id: str, factory_id: str | None = None,
        zone_id: str | None = None, scope: ScopeFilter | None = None,
    ) -> list[CameraEntity]: ...

    @abstractmethod
    async def get_by_id(
        self, camera_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> CameraEntity | None: ...

    @abstractmethod
    async def create(self, entity: CameraEntity) -> CameraEntity: ...

    @abstractmethod
    async def update(self, entity: CameraEntity) -> CameraEntity: ...

    @abstractmethod
    async def delete(self, camera_id: str, enterprise_id: str) -> None: ...

    @abstractmethod
    async def assign_worker(self, camera_id: str, worker_id: str | None) -> None: ...

    @abstractmethod
    async def list_by_worker(self, worker_id: int) -> list[CameraEntity]: ...

    @abstractmethod
    async def count_by_worker(self, worker_id: int) -> int: ...
