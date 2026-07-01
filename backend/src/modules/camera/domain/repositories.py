from abc import ABC, abstractmethod
from uuid import UUID

from src.modules.camera.domain.entities import CameraEntity


class ICameraRepository(ABC):

    @abstractmethod
    async def list(self, enterprise_id: UUID, factory_id: UUID | None = None, zone_id: UUID | None = None) -> list[CameraEntity]: ...

    @abstractmethod
    async def get_by_id(self, camera_id: UUID, enterprise_id: UUID) -> CameraEntity | None: ...

    @abstractmethod
    async def create(self, entity: CameraEntity) -> CameraEntity: ...

    @abstractmethod
    async def update(self, entity: CameraEntity) -> CameraEntity: ...

    @abstractmethod
    async def delete(self, camera_id: UUID, enterprise_id: UUID) -> None: ...

    @abstractmethod
    async def assign_worker(self, camera_id: UUID, worker_id: UUID | None) -> None: ...

    @abstractmethod
    async def list_by_worker(self, worker_id: UUID) -> list[CameraEntity]: ...

    @abstractmethod
    async def count_by_worker(self, worker_id: UUID) -> int: ...
