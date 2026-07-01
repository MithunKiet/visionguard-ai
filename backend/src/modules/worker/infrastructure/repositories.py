import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.worker.domain.entities import WorkerEntity
from src.shared.database.models import AIWorker


class WorkerRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_worker_id(self, worker_id: str) -> WorkerEntity | None:
        result = await self._db.execute(
            select(AIWorker).where(AIWorker.worker_id == worker_id)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_by_id(self, id: UUID) -> WorkerEntity | None:
        result = await self._db.execute(select(AIWorker).where(AIWorker.id == id))
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list_active(self, enterprise_id: UUID) -> list[WorkerEntity]:
        result = await self._db.execute(
            select(AIWorker).where(
                AIWorker.enterprise_id == enterprise_id,
                AIWorker.status == "Online",
            )
        )
        return [self._to_entity(r) for r in result.scalars()]

    async def list_all(self, enterprise_id: UUID) -> list[WorkerEntity]:
        result = await self._db.execute(
            select(AIWorker).where(AIWorker.enterprise_id == enterprise_id)
            .order_by(AIWorker.worker_id)
        )
        return [self._to_entity(r) for r in result.scalars()]

    async def upsert_heartbeat(
        self,
        enterprise_id: UUID,
        worker_id: str,
        hostname: str | None,
        model_version: str | None,
        gpu_available: bool,
    ) -> WorkerEntity:
        existing = await self.get_by_worker_id(worker_id)
        now = datetime.now(timezone.utc)

        if existing:
            await self._db.execute(
                update(AIWorker)
                .where(AIWorker.worker_id == worker_id)
                .values(
                    status="Online",
                    last_heartbeat=now,
                    hostname=hostname,
                    model_version=model_version,
                    gpu_available=gpu_available,
                )
            )
            await self._db.commit()
            return WorkerEntity(
                id=existing.id,
                enterprise_id=existing.enterprise_id,
                worker_id=worker_id,
                status="Online",
                hostname=hostname,
                model_version=model_version,
                gpu_available=gpu_available,
                last_heartbeat=now,
            )
        else:
            row = AIWorker(
                id=uuid.uuid4(),
                enterprise_id=enterprise_id,
                worker_id=worker_id,
                hostname=hostname,
                model_version=model_version,
                gpu_available=gpu_available,
                status="Online",
                last_heartbeat=now,
            )
            self._db.add(row)
            await self._db.commit()
            await self._db.refresh(row)
            return self._to_entity(row)

    async def mark_offline(self, worker_id: str) -> None:
        await self._db.execute(
            update(AIWorker)
            .where(AIWorker.worker_id == worker_id)
            .values(status="Offline")
        )
        await self._db.commit()

    @staticmethod
    def _to_entity(row: AIWorker) -> WorkerEntity:
        return WorkerEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            worker_id=row.worker_id,
            hostname=row.hostname,
            status=row.status,
            model_version=row.model_version,
            gpu_available=row.gpu_available,
            last_heartbeat=row.last_heartbeat,
        )
