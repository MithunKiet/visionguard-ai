from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.modules.department.domain.entities import DepartmentEntity


class IDepartmentRepository(ABC):

    @abstractmethod
    async def list(self, enterprise_id: UUID, factory_id: UUID | None = None) -> list[DepartmentEntity]: ...

    @abstractmethod
    async def get_by_id(self, department_id: UUID, enterprise_id: UUID) -> DepartmentEntity | None: ...

    @abstractmethod
    async def create(self, entity: DepartmentEntity) -> DepartmentEntity: ...

    @abstractmethod
    async def update(self, entity: DepartmentEntity) -> DepartmentEntity: ...

    @abstractmethod
    async def delete(self, department_id: UUID, enterprise_id: UUID) -> None: ...
