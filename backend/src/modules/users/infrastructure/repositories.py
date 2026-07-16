from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.domain.entities import UserAdminEntity
from src.shared.database.models import Department, Enterprise, Factory, Role, User, UserRole
from src.shared.database.pid import to_pk
from src.shared.security.scope import ScopeFilter, apply_factory_scope


class UserAdminRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def email_exists(self, email: str) -> bool:
        return (await self._db.scalar(select(User.id).where(User.email == email))) is not None

    async def list(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[UserAdminEntity]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(User, Factory.public_id, Factory.name, Department.public_id, Department.name)
            .outerjoin(Factory, Factory.id == User.factory_id)
            .outerjoin(Department, Department.id == User.department_id)
            .where(User.enterprise_id == ent_pk, User.deleted_at.is_(None))
            .order_by(User.name)
        )
        if scope is not None:
            q = await apply_factory_scope(self._db, q, scope, User.factory_id)
        rows = (await self._db.execute(q)).all()
        return [
            await self._to_entity(u, fac_pub, fac_name, dep_pub, dep_name, enterprise_id)
            for u, fac_pub, fac_name, dep_pub, dep_name in rows
        ]

    async def get_by_id(
        self, user_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> UserAdminEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(User, Factory.public_id, Factory.name, Department.public_id, Department.name)
            .outerjoin(Factory, Factory.id == User.factory_id)
            .outerjoin(Department, Department.id == User.department_id)
            .where(
                User.public_id == user_id,
                User.enterprise_id == ent_pk,
                User.deleted_at.is_(None),
            )
        )
        if scope is not None:
            q = await apply_factory_scope(self._db, q, scope, User.factory_id)
        row = (await self._db.execute(q)).first()
        if not row:
            return None
        u, fac_pub, fac_name, dep_pub, dep_name = row
        return await self._to_entity(u, fac_pub, fac_name, dep_pub, dep_name, enterprise_id)

    async def create(
        self, entity: UserAdminEntity, password_hash: str, invited_by_public_id: str,
    ) -> UserAdminEntity:
        ent_pk = await to_pk(self._db, Enterprise, entity.enterprise_id)
        factory_pk = await to_pk(self._db, Factory, entity.factory_id)
        department_pk = await to_pk(self._db, Department, entity.department_id)
        invited_by_pk = await to_pk(self._db, User, invited_by_public_id)

        row = User(
            enterprise_id=ent_pk,
            name=entity.name,
            email=entity.email,
            password_hash=password_hash,
            factory_id=factory_pk,
            department_id=department_pk,
            assigned_zone_ids=entity.assigned_zone_ids or [],
            status=entity.status,
            is_first_login=True,
            # Only the very first enterprise admin (enterprise onboarding)
            # goes through the setup wizard — an invited user joins an
            # already-configured enterprise, so skip straight past it.
            setup_completed=True,
            invited_by=invited_by_pk,
            invited_at=datetime.now(timezone.utc),
        )
        self._db.add(row)
        await self._db.flush()

        for role_code in entity.roles:
            role = (await self._db.execute(select(Role).where(Role.code == role_code))).scalar_one()
            self._db.add(UserRole(user_public_id=row.public_id, role_public_id=role.public_id))
        await self._db.commit()

        return await self.get_by_id(row.public_id, entity.enterprise_id)

    async def update(
        self, user_id: str, enterprise_id: str, fields: dict, role_codes: list[str] | None,
    ) -> UserAdminEntity:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        values: dict = {}
        if "name" in fields:
            values["name"] = fields["name"]
        if "status" in fields:
            values["status"] = fields["status"]
        if "factory_id" in fields:
            values["factory_id"] = await to_pk(self._db, Factory, fields["factory_id"])
        if "department_id" in fields:
            values["department_id"] = await to_pk(self._db, Department, fields["department_id"])
        if "assigned_zone_ids" in fields:
            values["assigned_zone_ids"] = fields["assigned_zone_ids"]
        if values:
            await self._db.execute(
                update(User).where(User.public_id == user_id, User.enterprise_id == ent_pk).values(**values)
            )

        if role_codes is not None:
            # UserRole is keyed directly by public_ids (see models.py) — no
            # internal-id resolution needed for this replace-all-roles step.
            await self._db.execute(delete(UserRole).where(UserRole.user_public_id == user_id))
            for role_code in role_codes:
                role = (await self._db.execute(select(Role).where(Role.code == role_code))).scalar_one()
                self._db.add(UserRole(user_public_id=user_id, role_public_id=role.public_id))

        await self._db.commit()
        return await self.get_by_id(user_id, enterprise_id)

    async def deactivate(self, user_id: str, enterprise_id: str) -> None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(User).where(User.public_id == user_id, User.enterprise_id == ent_pk)
            .values(status="Inactive", deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def _to_entity(
        self, u: User, factory_public_id: str | None, factory_name: str | None,
        department_public_id: str | None, department_name: str | None, enterprise_id: str,
    ) -> UserAdminEntity:
        roles_result = await self._db.execute(
            select(Role.code)
            .join(UserRole, UserRole.role_public_id == Role.public_id)
            .where(UserRole.user_public_id == u.public_id)
        )
        roles = [r[0] for r in roles_result.all()]
        return UserAdminEntity(
            id=u.public_id,
            enterprise_id=enterprise_id,
            name=u.name,
            email=u.email,
            status=u.status,
            roles=roles,
            factory_id=factory_public_id,
            factory_name=factory_name,
            department_id=department_public_id,
            department_name=department_name,
            assigned_zone_ids=u.assigned_zone_ids or [],
            is_first_login=u.is_first_login,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
            deleted_at=u.deleted_at,
        )
