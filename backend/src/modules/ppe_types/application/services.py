"""
PpeTypeService — the enterprise-defined catalog of PPE items. Zones and
cameras reference these by `code`; actual detectability of a code still
depends on what the AI worker's loaded model can recognize (see
ai-worker/src/pipeline/ppe_validator.py — an undetected code just never
fires a violation, it isn't rejected here).
"""
import re

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, VisionGuardException
from src.shared.database.models import Enterprise, PpeType
from src.shared.database.pid import to_pk

log = structlog.get_logger()

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    return slug or "ppe_type"


class PpeTypeService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_types(self, enterprise_id: str, include_inactive: bool = False) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(PpeType).where(PpeType.enterprise_id == ent_pk)
        if not include_inactive:
            q = q.where(PpeType.is_active.is_(True))
        rows = (await self._db.execute(q.order_by(PpeType.name))).scalars()
        return [self.to_dict(r) for r in rows]

    async def create_type(self, enterprise_id: str, name: str, created_by: str) -> dict:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        code = _slugify(name)
        existing = (await self._db.execute(
            select(PpeType).where(PpeType.enterprise_id == ent_pk, PpeType.code == code)
        )).scalar_one_or_none()
        if existing:
            raise VisionGuardException(
                code="PPE_TYPE_ALREADY_EXISTS",
                message=f"A PPE type with code '{code}' already exists",
                status_code=409,
            )

        row = PpeType(
            enterprise_id=ent_pk, code=code, name=name.strip(),
            is_active=True, created_by=str(created_by),
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("ppe_type.created", code=code, enterprise_id=str(enterprise_id))
        return self.to_dict(row)

    async def update_type(
        self, type_id: str, enterprise_id: str, name: str | None = None, is_active: bool | None = None,
    ) -> dict:
        row = await self._get_row(type_id, enterprise_id)
        if name is not None:
            row.name = name.strip()
        if is_active is not None:
            row.is_active = is_active
        await self._db.commit()
        await self._db.refresh(row)
        return self.to_dict(row)

    async def _get_row(self, type_id: str, enterprise_id: str) -> PpeType:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        row = (await self._db.execute(
            select(PpeType).where(PpeType.public_id == type_id, PpeType.enterprise_id == ent_pk)
        )).scalar_one_or_none()
        if not row:
            raise NotFoundException("PpeType", str(type_id))
        return row

    @staticmethod
    def to_dict(t: PpeType) -> dict:
        return {
            "id": t.public_id,
            "code": t.code,
            "name": t.name,
            "is_active": t.is_active,
        }
