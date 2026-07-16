from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.entities import UserEntity
from src.modules.identity.domain.repositories import IUserRepository
from src.shared.database.models import Department, Enterprise, Factory, Role, User, UserRole


class UserRepository(IUserRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_email(self, email: str) -> UserEntity | None:
        result = await self._db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def get_by_id(self, user_id: str) -> UserEntity | None:
        result = await self._db.execute(
            select(User).where(User.public_id == user_id, User.deleted_at.is_(None))
        )
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def update_last_login(self, user_id: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.public_id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def update_password(self, user_id: str, new_hash: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.public_id == user_id)
            .values(
                password_hash=new_hash,
                password_changed_at=datetime.now(timezone.utc),
                is_first_login=False,
            )
        )
        await self._db.commit()

    async def get_internal_id(self, user_id: str) -> int | None:
        """SQL-boundary helper — resolves a public_id to the internal integer
        id for callers that need to write an FK column (e.g. refresh_tokens.user_id)."""
        return await self._db.scalar(select(User.id).where(User.public_id == user_id))

    async def _to_entity(self, row: User) -> UserEntity:
        roles_result = await self._db.execute(
            select(Role.code)
            .join(UserRole, UserRole.role_public_id == Role.public_id)
            .where(UserRole.user_public_id == row.public_id)
        )
        roles = [r[0] for r in roles_result.all()]

        enterprise_public_id = await self._db.scalar(
            select(Enterprise.public_id).where(Enterprise.id == row.enterprise_id)
        )
        factory_public_id = None
        if row.factory_id:
            factory_public_id = await self._db.scalar(
                select(Factory.public_id).where(Factory.id == row.factory_id)
            )
        department_public_id = None
        if row.department_id:
            department_public_id = await self._db.scalar(
                select(Department.public_id).where(Department.id == row.department_id)
            )

        return UserEntity(
            id=row.public_id,
            enterprise_id=enterprise_public_id,
            name=row.name,
            email=row.email,
            roles=roles,
            status=row.status,
            password_hash=row.password_hash,
            is_first_login=row.is_first_login,
            totp_enabled=row.totp_enabled,
            last_login_at=row.last_login_at,
            deleted_at=row.deleted_at,
            factory_id=factory_public_id,
            department_id=department_public_id,
            assigned_zone_ids=row.assigned_zone_ids or [],
        )
