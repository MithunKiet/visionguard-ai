from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.worker.domain.entities import WorkerEntity
from src.shared.database.models import AIWorker, Enterprise, Factory


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

    async def get_internal_id_by_worker_id(self, worker_id: str, enterprise_id: str | None = None) -> int | None:
        """SQL-boundary helper — resolves a worker's business id (e.g.
        "worker-1") to the internal integer id other tables FK against."""
        query = select(AIWorker.id).where(AIWorker.worker_id == worker_id)
        if enterprise_id:
            query = query.join(Enterprise, Enterprise.id == AIWorker.enterprise_id).where(
                Enterprise.public_id == enterprise_id
            )
        return await self._db.scalar(query)

    async def get_internal_id(self, public_id: str) -> int | None:
        """SQL-boundary helper — resolves a worker's public_id to the
        internal integer id other tables FK against."""
        return await self._db.scalar(select(AIWorker.id).where(AIWorker.public_id == public_id))

    async def list_active(self, enterprise_id: str) -> list[WorkerEntity]:
        ent_pk = await self._resolve_enterprise_pk(enterprise_id)
        result = await self._db.execute(
            select(AIWorker, Factory.public_id).outerjoin(Factory, Factory.id == AIWorker.factory_id).where(
                AIWorker.enterprise_id == ent_pk,
                AIWorker.status == "Online",
                AIWorker.last_heartbeat > datetime.now(timezone.utc) - timedelta(seconds=60),
                AIWorker.deleted_at.is_(None), AIWorker.is_active.is_(True),
            )
        )
        return [self._to_entity_sync(r, enterprise_id, factory_id) for r, factory_id in result.all()]

    async def list_all(self, enterprise_id: str) -> list[WorkerEntity]:
        ent_pk = await self._resolve_enterprise_pk(enterprise_id)
        result = await self._db.execute(
            select(AIWorker, Factory.public_id).outerjoin(Factory, Factory.id == AIWorker.factory_id)
            .where(AIWorker.enterprise_id == ent_pk, AIWorker.deleted_at.is_(None))
            .order_by(AIWorker.worker_id)
        )
        return [self._to_entity_sync(r, enterprise_id, factory_id) for r, factory_id in result.all()]

    async def upsert_heartbeat(
        self,
        enterprise_id: str,
        worker_id: str,
        hostname: str | None,
        model_version: str | None,
        gpu_available: bool,
    ) -> WorkerEntity:
        existing = await self._db.execute(
            # Business IDs are globally unique. Find collisions before the
            # tenant check so a foreign heartbeat is rejected, not inserted.
            select(AIWorker).where(AIWorker.worker_id == worker_id)
        )
        existing_row = existing.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if existing_row:
            ent_pk = await self._resolve_enterprise_pk(enterprise_id)
            if existing_row.enterprise_id != ent_pk:
                from src.core.exceptions import ForbiddenException
                raise ForbiddenException("Worker belongs to another enterprise")
            await self._db.execute(
                update(AIWorker)
                .where(AIWorker.worker_id == worker_id, AIWorker.enterprise_id == existing_row.enterprise_id)
                .values(
                    status="Online",
                    last_heartbeat=now,
                    hostname=hostname,
                    model_version=model_version,
                    gpu_available=gpu_available,
                )
            )
            await self._db.commit()
            await self._db.refresh(existing_row)
            return await self._to_entity(existing_row)
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
        factory_public_id = await self._db.scalar(select(Factory.public_id).where(
            Factory.id == row.factory_id,
        )) if row.factory_id is not None else None
        return self._to_entity_sync(row, enterprise_public_id, factory_public_id)

    @staticmethod
    def _to_entity_sync(row: AIWorker, enterprise_public_id: str, factory_public_id: str | None = None) -> WorkerEntity:
        return WorkerEntity(
            id=row.public_id,
            enterprise_id=enterprise_public_id,
            worker_id=row.worker_id,
            hostname=row.hostname,
            status=row.status,
            model_version=row.model_version,
            gpu_available=row.gpu_available,
            last_heartbeat=row.last_heartbeat,
            factory_id=factory_public_id,
            max_cameras=row.max_cameras,
        )
