"""
EnterpriseService — dynamic branding (master context rules #1, #2): all
company names, logos, and colors live in the enterprises table and are
served from here at runtime. Nothing is hardcoded anywhere in the platform.
"""
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.shared.database.models import Enterprise

log = structlog.get_logger()

_BRANDING_FIELDS = ("name", "tagline", "primary_color", "secondary_color", "logo_url", "favicon_url")


class EnterpriseService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_branding(self, enterprise_id: UUID) -> dict:
        return self.to_branding(await self._get_row(enterprise_id))

    async def update_branding(self, enterprise_id: UUID, changes: dict) -> dict:
        row = await self._get_row(enterprise_id)
        for field in _BRANDING_FIELDS:
            if changes.get(field) is not None:
                setattr(row, field, changes[field])
        await self._db.commit()
        await self._db.refresh(row)
        log.info("enterprise.branding_updated", enterprise_id=str(enterprise_id))
        return self.to_branding(row)

    async def _get_row(self, enterprise_id: UUID) -> Enterprise:
        row = (await self._db.execute(
            select(Enterprise).where(Enterprise.id == enterprise_id)
        )).scalar_one_or_none()
        if not row:
            raise NotFoundException("Enterprise", str(enterprise_id))
        return row

    @staticmethod
    def to_branding(e: Enterprise) -> dict:
        return {
            "id": str(e.id),
            "name": e.name,
            "code": e.code,
            "tagline": e.tagline,
            "logo_url": e.logo_url,
            "favicon_url": e.favicon_url,
            "primary_color": e.primary_color,
            "secondary_color": e.secondary_color,
        }
