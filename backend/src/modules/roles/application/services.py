"""
RoleService — read access to the platform-wide roles catalog. See
src/shared/database/models.py Role for why this is global, not
enterprise-scoped, and why it's reference data rather than something that
grants permissions on its own.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database.models import Role


class RoleService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_roles(self, include_inactive: bool = False) -> list[dict]:
        q = select(Role)
        if not include_inactive:
            q = q.where(Role.is_active.is_(True))
        rows = (await self._db.execute(q.order_by(Role.name))).scalars()
        return [self.to_dict(r) for r in rows]

    @staticmethod
    def to_dict(r: Role) -> dict:
        return {
            "id": r.public_id,
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "scope": r.scope,
            "is_active": r.is_active,
        }
