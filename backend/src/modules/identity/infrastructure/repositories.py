from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.entities import UserEntity
from src.modules.identity.domain.repositories import IUserRepository
from src.shared.database.models import User


class UserRepository(IUserRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_email(self, email: str) -> UserEntity | None:
        result = await self._db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_by_id(self, user_id: UUID) -> UserEntity | None:
        result = await self._db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def update_last_login(self, user_id: UUID) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def update_password(self, user_id: UUID, new_hash: str) -> None:
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                password_hash=new_hash,
                password_changed_at=datetime.now(timezone.utc),
                is_first_login=False,
            )
        )
        await self._db.commit()

    @staticmethod
    def _to_entity(row: User) -> UserEntity:
        return UserEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            name=row.name,
            email=row.email,
            role=row.role,
            status=row.status,
            password_hash=row.password_hash,
            is_first_login=row.is_first_login,
            totp_enabled=row.totp_enabled,
            last_login_at=row.last_login_at,
            deleted_at=row.deleted_at,
        )
