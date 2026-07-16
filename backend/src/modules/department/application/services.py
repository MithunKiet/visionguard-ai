"""
DepartmentService — CRUD for factory departments.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.modules.department.domain.entities import DepartmentEntity
from src.modules.department.infrastructure.repositories import DepartmentRepository
from src.shared.database.models import Department, Enterprise, Factory, User
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_factory_scope

log = structlog.get_logger()


class DepartmentService:

    def __init__(self, repo: DepartmentRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    async def list_departments(
        self, enterprise_id: str, factory_id: str | None = None, scope: ScopeFilter | None = None,
    ) -> list[DepartmentEntity]:
        return await self._repo.list(enterprise_id, factory_id, scope)

    async def list_departments_with_factory_name(
        self, enterprise_id: str, factory_id: str | None = None, scope: ScopeFilter | None = None,
    ) -> list[dict]:
        """Same rows as list_departments, with the factory's name embedded —
        for the admin table, which otherwise only has a bare factory_id."""
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(Department, Factory.name, Factory.public_id)
            .join(Factory, Factory.id == Department.factory_id)
            .where(Department.enterprise_id == ent_pk, Department.deleted_at.is_(None))
            .order_by(Factory.name, Department.name)
        )
        if factory_id:
            q = q.where(Department.factory_id == await to_pk(self._db, Factory, factory_id))
        if scope is not None:
            q = await apply_factory_scope(self._db, q, scope, Department.factory_id)
        rows = (await self._db.execute(q)).all()

        result = []
        for d, factory_name, factory_public_id in rows:
            head_public_id = await to_public_id(self._db, User, d.head_user_id)
            result.append({
                "id": d.public_id,
                "enterprise_id": enterprise_id,
                "factory_id": factory_public_id,
                "name": d.name,
                "code": d.code,
                "head_user_id": head_public_id,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "factory_name": factory_name,
            })
        return result

    async def get_department(self, department_id: str, enterprise_id: str) -> DepartmentEntity:
        department = await self._repo.get_by_id(department_id, enterprise_id)
        if not department:
            raise NotFoundException("Department", str(department_id))
        return department

    async def create_department(
        self,
        enterprise_id: str,
        factory_id: str,
        name: str,
        code: str,
        head_user_id: str | None = None,
    ) -> DepartmentEntity:
        entity = DepartmentEntity(
            enterprise_id=enterprise_id,
            factory_id=factory_id,
            name=name,
            code=code,
            head_user_id=head_user_id,
        )
        department = await self._repo.create(entity)
        log.info("department.created", department_id=str(department.id), name=name)
        return department

    async def update_department(self, department_id: str, enterprise_id: str, **fields) -> DepartmentEntity:
        department = await self.get_department(department_id, enterprise_id)
        for key, val in fields.items():
            if val is not None and hasattr(department, key):
                setattr(department, key, val)
        return await self._repo.update(department)

    async def delete_department(self, department_id: str, enterprise_id: str) -> None:
        await self.get_department(department_id, enterprise_id)
        await self._repo.delete(department_id, enterprise_id)
        log.info("department.deleted", department_id=str(department_id))

    @staticmethod
    def to_dict(d: DepartmentEntity) -> dict:
        return {
            "id": d.id,
            "enterprise_id": d.enterprise_id,
            "factory_id": d.factory_id,
            "name": d.name,
            "code": d.code,
            "head_user_id": d.head_user_id,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
