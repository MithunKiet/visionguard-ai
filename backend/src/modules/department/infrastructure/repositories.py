from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.department.domain.entities import DepartmentEntity
from src.modules.department.domain.repositories import IDepartmentRepository
from src.shared.database.models import Department


class DepartmentRepository(IDepartmentRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(self, enterprise_id: UUID, factory_id: UUID | None = None) -> list[DepartmentEntity]:
        q = select(Department).where(
            Department.enterprise_id == enterprise_id, Department.deleted_at.is_(None)
        )
        if factory_id:
            q = q.where(Department.factory_id == factory_id)
        result = await self._db.execute(q.order_by(Department.name))
        return [self._to_entity(r) for r in result.scalars()]

    async def get_by_id(self, department_id: UUID, enterprise_id: UUID) -> DepartmentEntity | None:
        result = await self._db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.enterprise_id == enterprise_id,
                Department.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def create(self, entity: DepartmentEntity) -> DepartmentEntity:
        row = Department(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            factory_id=entity.factory_id,
            name=entity.name,
            code=entity.code,
            head_user_id=entity.head_user_id,
            status=entity.status,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def update(self, entity: DepartmentEntity) -> DepartmentEntity:
        await self._db.execute(
            update(Department).where(Department.id == entity.id).values(
                name=entity.name,
                head_user_id=entity.head_user_id,
                status=entity.status,
                modified_on=datetime.now(timezone.utc),
                version=Department.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, department_id: UUID, enterprise_id: UUID) -> None:
        await self._db.execute(
            update(Department).where(
                Department.id == department_id,
                Department.enterprise_id == enterprise_id,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    @staticmethod
    def _to_entity(row: Department) -> DepartmentEntity:
        return DepartmentEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            factory_id=row.factory_id,
            name=row.name,
            code=row.code,
            status=row.status,
            head_user_id=row.head_user_id,
            created_on=row.created_on,
            modified_on=row.modified_on,
            deleted_at=row.deleted_at,
        )
