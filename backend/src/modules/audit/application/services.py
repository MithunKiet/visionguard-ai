"""
AuditService — append-only compliance trail (master context rule #7).

Rows are only ever inserted; there is no update/delete path anywhere in the
codebase. `record()` never raises — a failed audit write must not break the
business action it documents, it is logged loudly instead.

Callers pass public_id strings (external identifiers); this service resolves
them to the internal integer ids that AuditLog.enterprise_id/user_id FK to.
`entity_id` is stored as-is (a public_id string) since it can point at any
table's row and is not FK-constrained.
"""
from datetime import datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database.models import AuditLog, Enterprise, User

log = structlog.get_logger()


class AuditService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def record(
        self,
        enterprise_id: str,
        user_id: str | None,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        try:
            ent_pk = await self._db.scalar(
                select(Enterprise.id).where(Enterprise.public_id == str(enterprise_id))
            )
            user_pk = None
            if user_id:
                user_pk = await self._db.scalar(
                    select(User.id).where(User.public_id == str(user_id))
                )
            self._db.add(AuditLog(
                enterprise_id=ent_pk,
                user_id=user_pk,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id else None,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
            ))
            await self._db.commit()
        except Exception as e:
            log.error("audit.write_failed", action=action, error=str(e))

    async def list(
        self,
        enterprise_id: str,
        action: str | None = None,
        user_id: str | None = None,
        entity_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        ent_pk = await self._db.scalar(
            select(Enterprise.id).where(Enterprise.public_id == str(enterprise_id))
        )
        q = select(AuditLog).where(AuditLog.enterprise_id == ent_pk)
        if action:
            q = q.where(AuditLog.action == action)
        if user_id:
            user_pk = await self._db.scalar(
                select(User.id).where(User.public_id == str(user_id))
            )
            q = q.where(AuditLog.user_id == user_pk)
        if entity_type:
            q = q.where(AuditLog.entity_type == entity_type)
        if from_dt:
            q = q.where(AuditLog.timestamp >= from_dt)
        if to_dt:
            q = q.where(AuditLog.timestamp <= to_dt)

        total = (await self._db.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one()

        q = q.order_by(AuditLog.timestamp.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(q)).scalars()
        return [await self._to_dict(r) for r in rows], total

    async def _to_dict(self, r: AuditLog) -> dict:
        user_public_id = None
        if r.user_id:
            user_public_id = await self._db.scalar(
                select(User.public_id).where(User.id == r.user_id)
            )
        return {
            "id": r.public_id,
            "user_id": user_public_id,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "ip_address": r.ip_address,
            "user_agent": r.user_agent,
            "correlation_id": r.correlation_id,
            "timestamp": r.timestamp.isoformat(),
        }
