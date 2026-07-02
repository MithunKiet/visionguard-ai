"""
AuditService — append-only compliance trail (master context rule #7).

Rows are only ever inserted; there is no update/delete path anywhere in the
codebase. `record()` never raises — a failed audit write must not break the
business action it documents, it is logged loudly instead.
"""
import uuid
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database.models import AuditLog

log = structlog.get_logger()


class AuditService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def record(
        self,
        enterprise_id: UUID,
        user_id: UUID | None,
        action: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        old_value: dict | None = None,
        new_value: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        try:
            self._db.add(AuditLog(
                id=uuid.uuid4(),
                enterprise_id=enterprise_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
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
        enterprise_id: UUID,
        action: str | None = None,
        user_id: UUID | None = None,
        entity_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        q = select(AuditLog).where(AuditLog.enterprise_id == enterprise_id)
        if action:
            q = q.where(AuditLog.action == action)
        if user_id:
            q = q.where(AuditLog.user_id == user_id)
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
        return [self._to_dict(r) for r in rows], total

    @staticmethod
    def _to_dict(r: AuditLog) -> dict:
        return {
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": str(r.entity_id) if r.entity_id else None,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "ip_address": r.ip_address,
            "user_agent": r.user_agent,
            "correlation_id": r.correlation_id,
            "timestamp": r.timestamp.isoformat(),
        }
