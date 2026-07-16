from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.department.domain.entities import DepartmentEntity
from src.modules.department.domain.repositories import IDepartmentRepository
from src.shared.database.models import Department, Enterprise, Factory, User
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_factory_scope


class DepartmentRepository(IDepartmentRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(
        self, enterprise_id: str, factory_id: str | None = None, scope: ScopeFilter | None = None,
    ) -> list[DepartmentEntity]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(Department).where(
            Department.enterprise_id == ent_pk, Department.deleted_at.is_(None)
        )
        if factory_id:
            q = q.where(Department.factory_id == await to_pk(self._db, Factory, factory_id))
        if scope is not None:
            q = await apply_factory_scope(self._db, q, scope, Department.factory_id)
        result = await self._db.execute(q.order_by(Department.name))
        return [await self._to_entity(r) for r in result.scalars()]

    async def get_by_id(self, department_id: str, enterprise_id: str) -> DepartmentEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        result = await self._db.execute(
            select(Department).where(
                Department.public_id == department_id,
                Department.enterprise_id == ent_pk,
                Department.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def create(self, entity: DepartmentEntity) -> DepartmentEntity:
        row = Department(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            factory_id=await to_pk(self._db, Factory, entity.factory_id),
            name=entity.name,
            code=entity.code,
            head_user_id=await to_pk(self._db, User, entity.head_user_id),
            status=entity.status,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return await self._to_entity(row)

    async def update(self, entity: DepartmentEntity) -> DepartmentEntity:
        await self._db.execute(
            update(Department).where(Department.public_id == entity.id).values(
                name=entity.name,
                head_user_id=await to_pk(self._db, User, entity.head_user_id),
                status=entity.status,
                updated_at=datetime.now(timezone.utc),
                version=Department.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, department_id: str, enterprise_id: str) -> None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(Department).where(
                Department.public_id == department_id,
                Department.enterprise_id == ent_pk,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def _to_entity(self, row: Department) -> DepartmentEntity:
        return DepartmentEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            factory_id=await to_public_id(self._db, Factory, row.factory_id),
            name=row.name,
            code=row.code,
            status=row.status,
            head_user_id=await to_public_id(self._db, User, row.head_user_id),
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )
