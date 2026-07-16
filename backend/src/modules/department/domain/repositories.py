from __future__ import annotations

from abc import ABC, abstractmethod

from src.modules.department.domain.entities import DepartmentEntity
from src.shared.security.scope import ScopeFilter


class IDepartmentRepository(ABC):

    @abstractmethod
    async def list(
        self, enterprise_id: str, factory_id: str | None = None, scope: ScopeFilter | None = None,
    ) -> list[DepartmentEntity]: ...

    @abstractmethod
    async def get_by_id(self, department_id: str, enterprise_id: str) -> DepartmentEntity | None: ...

    @abstractmethod
    async def create(self, entity: DepartmentEntity) -> DepartmentEntity: ...

    @abstractmethod
    async def update(self, entity: DepartmentEntity) -> DepartmentEntity: ...

    @abstractmethod
    async def delete(self, department_id: str, enterprise_id: str) -> None: ...
