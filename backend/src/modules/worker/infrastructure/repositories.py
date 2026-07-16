from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.worker.domain.entities import WorkerEntity
from src.shared.database.models import AIWorker, Enterprise


class WorkerRepository:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_by_worker_id(self, worker_id: str) -> WorkerEntity | None:
        result = await self._db.execute(
            select(AIWorker).where(AIWorker.worker_id == worker_id)
        )
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def get_by_id(self, public_id: str) -> WorkerEntity | None:
        result = await self._db.execute(select(AIWorker).where(AIWorker.public_id == public_id))
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def get_internal_id_by_worker_id(self, worker_id: str) -> int | None:
        """SQL-boundary helper — resolves a worker's business id (e.g.
        "worker-1") to the internal integer id other tables FK against."""
        return await self._db.scalar(select(AIWorker.id).where(AIWorker.worker_id == worker_id))

    async def get_internal_id(self, public_id: str) -> int | None:
        """SQL-boundary helper — resolves a worker's public_id to the
        internal integer id other tables FK against."""
        return await self._db.scalar(select(AIWorker.id).where(AIWorker.public_id == public_id))

    async def list_active(self, enterprise_id: str) -> list[WorkerEntity]:
        ent_pk = await self._resolve_enterprise_pk(enterprise_id)
        result = await self._db.execute(
            select(AIWorker).where(
                AIWorker.enterprise_id == ent_pk,
                AIWorker.status == "Online",
            )
        )
        return [self._to_entity_sync(r, enterprise_id) for r in result.scalars()]

    async def list_all(self, enterprise_id: str) -> list[WorkerEntity]:
        ent_pk = await self._resolve_enterprise_pk(enterprise_id)
        result = await self._db.execute(
            select(AIWorker).where(AIWorker.enterprise_id == ent_pk)
            .order_by(AIWorker.worker_id)
        )
        return [self._to_entity_sync(r, enterprise_id) for r in result.scalars()]

    async def upsert_heartbeat(
        self,
        enterprise_id: str,
        worker_id: str,
        hostname: str | None,
        model_version: str | None,
        gpu_available: bool,
    ) -> WorkerEntity:
        existing = await self._db.execute(
            select(AIWorker).where(AIWorker.worker_id == worker_id)
        )
        existing_row = existing.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if existing_row:
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
                id=existing_row.public_id,
                enterprise_id=enterprise_id,
                worker_id=worker_id,
                status="Online",
                hostname=hostname,
                model_version=model_version,
                gpu_available=gpu_available,
                last_heartbeat=now,
            )
        else:
            ent_pk = await self._resolve_enterprise_pk(enterprise_id)
            row = AIWorker(
                enterprise_id=ent_pk,
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
            return self._to_entity_sync(row, enterprise_id)

    async def mark_offline(self, worker_id: str) -> None:
        await self._db.execute(
            update(AIWorker)
            .where(AIWorker.worker_id == worker_id)
            .values(status="Offline")
        )
        await self._db.commit()

    async def _resolve_enterprise_pk(self, enterprise_id: str) -> int | None:
        return await self._db.scalar(
            select(Enterprise.id).where(Enterprise.public_id == enterprise_id)
        )

    async def _to_entity(self, row: AIWorker) -> WorkerEntity:
        enterprise_public_id = await self._db.scalar(
            select(Enterprise.public_id).where(Enterprise.id == row.enterprise_id)
        )
        return self._to_entity_sync(row, enterprise_public_id)

    @staticmethod
    def _to_entity_sync(row: AIWorker, enterprise_public_id: str) -> WorkerEntity:
        return WorkerEntity(
            id=row.public_id,
            enterprise_id=enterprise_public_id,
            worker_id=row.worker_id,
            hostname=row.hostname,
            status=row.status,
            model_version=row.model_version,
            gpu_available=row.gpu_available,
            last_heartbeat=row.last_heartbeat,
        )
