"""
DepartmentService — CRUD for factory departments.
"""
import uuid
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.modules.department.domain.entities import DepartmentEntity
from src.modules.department.infrastructure.repositories import DepartmentRepository
from src.shared.database.models import Department, Factory

log = structlog.get_logger()


class DepartmentService:

    def __init__(self, repo: DepartmentRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    async def list_departments(self, enterprise_id: UUID, factory_id: UUID | None = None) -> list[DepartmentEntity]:
        return await self._repo.list(enterprise_id, factory_id)

    async def list_departments_with_factory_name(
        self, enterprise_id: UUID, factory_id: UUID | None = None
    ) -> list[dict]:
        """Same rows as list_departments, with the factory's name embedded —
        for the admin table, which otherwise only has a bare factory_id."""
        q = (
            select(Department, Factory.name)
            .join(Factory, Factory.id == Department.factory_id)
            .where(Department.enterprise_id == enterprise_id, Department.deleted_at.is_(None))
            .order_by(Factory.name, Department.name)
        )
        if factory_id:
            q = q.where(Department.factory_id == factory_id)
        rows = (await self._db.execute(q)).all()
        return [
            {**self.to_dict(DepartmentRepository._to_entity(d)), "factory_name": factory_name}
            for d, factory_name in rows
        ]

    async def get_department(self, department_id: UUID, enterprise_id: UUID) -> DepartmentEntity:
        department = await self._repo.get_by_id(department_id, enterprise_id)
        if not department:
            raise NotFoundException("Department", str(department_id))
        return department

    async def create_department(
        self,
        enterprise_id: UUID,
        factory_id: UUID,
        name: str,
        code: str,
        head_user_id: UUID | None = None,
    ) -> DepartmentEntity:
        entity = DepartmentEntity(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            factory_id=factory_id,
            name=name,
            code=code,
            head_user_id=head_user_id,
        )
        department = await self._repo.create(entity)
        log.info("department.created", department_id=str(department.id), name=name)
        return department

    async def update_department(self, department_id: UUID, enterprise_id: UUID, **fields) -> DepartmentEntity:
        department = await self.get_department(department_id, enterprise_id)
        for key, val in fields.items():
            if val is not None and hasattr(department, key):
                setattr(department, key, val)
        return await self._repo.update(department)

    async def delete_department(self, department_id: UUID, enterprise_id: UUID) -> None:
        await self.get_department(department_id, enterprise_id)
        await self._repo.delete(department_id, enterprise_id)
        log.info("department.deleted", department_id=str(department_id))

    @staticmethod
    def to_dict(d: DepartmentEntity) -> dict:
        return {
            "id": str(d.id),
            "enterprise_id": str(d.enterprise_id),
            "factory_id": str(d.factory_id),
            "name": d.name,
            "code": d.code,
            "head_user_id": str(d.head_user_id) if d.head_user_id else None,
            "status": d.status,
            "created_on": d.created_on.isoformat() if d.created_on else None,
            "modified_on": d.modified_on.isoformat() if d.modified_on else None,
        }
