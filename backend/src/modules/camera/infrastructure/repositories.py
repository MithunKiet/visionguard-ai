import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.camera.domain.entities import CameraEntity
from src.modules.camera.domain.repositories import ICameraRepository
from src.shared.database.models import Camera


class CameraRepository(ICameraRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(
        self,
        enterprise_id: UUID,
        factory_id: UUID | None = None,
        zone_id: UUID | None = None,
    ) -> list[CameraEntity]:
        q = select(Camera).where(
            Camera.enterprise_id == enterprise_id,
            Camera.deleted_at.is_(None),
        )
        if factory_id:
            q = q.where(Camera.factory_id == factory_id)
        if zone_id:
            q = q.where(Camera.zone_id == zone_id)
        result = await self._db.execute(q.order_by(Camera.name))
        return [self._to_entity(r) for r in result.scalars()]

    async def get_by_id(self, camera_id: UUID, enterprise_id: UUID) -> CameraEntity | None:
        result = await self._db.execute(
            select(Camera).where(
                Camera.id == camera_id,
                Camera.enterprise_id == enterprise_id,
                Camera.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def create(self, entity: CameraEntity) -> CameraEntity:
        row = Camera(
            id=entity.id,
            enterprise_id=entity.enterprise_id,
            factory_id=entity.factory_id,
            zone_id=entity.zone_id,
            name=entity.name,
            code=entity.code,
            rtsp_url=entity.rtsp_url,
            camera_type=entity.camera_type,
            position_desc=entity.position_desc,
            status=entity.status,
            fps=entity.fps,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return self._to_entity(row)

    async def update(self, entity: CameraEntity) -> CameraEntity:
        await self._db.execute(
            update(Camera).where(Camera.id == entity.id).values(
                name=entity.name,
                rtsp_url=entity.rtsp_url,
                camera_type=entity.camera_type,
                position_desc=entity.position_desc,
                status=entity.status,
                fps=entity.fps,
                in_maintenance=entity.in_maintenance,
                maintenance_until=entity.maintenance_until,
                modified_on=datetime.now(timezone.utc),
                version=Camera.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def delete(self, camera_id: UUID, enterprise_id: UUID) -> None:
        await self._db.execute(
            update(Camera).where(
                Camera.id == camera_id,
                Camera.enterprise_id == enterprise_id,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def assign_worker(self, camera_id: UUID, worker_id: UUID | None) -> None:
        await self._db.execute(
            update(Camera).where(Camera.id == camera_id).values(worker_id=worker_id)
        )
        await self._db.commit()

    async def list_by_worker(self, worker_id: UUID) -> list[CameraEntity]:
        result = await self._db.execute(
            select(Camera).where(
                Camera.worker_id == worker_id,
                Camera.deleted_at.is_(None),
            )
        )
        return [self._to_entity(r) for r in result.scalars()]

    async def count_by_worker(self, worker_id: UUID) -> int:
        result = await self._db.execute(
            select(func.count()).where(
                Camera.worker_id == worker_id,
                Camera.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    @staticmethod
    def _to_entity(row: Camera) -> CameraEntity:
        return CameraEntity(
            id=row.id,
            enterprise_id=row.enterprise_id,
            factory_id=row.factory_id,
            zone_id=row.zone_id,
            worker_id=row.worker_id,
            name=row.name,
            code=row.code,
            rtsp_url=row.rtsp_url,
            camera_type=row.camera_type,
            position_desc=row.position_desc,
            status=row.status,
            fps=row.fps,
            in_maintenance=row.in_maintenance,
            maintenance_until=row.maintenance_until,
            last_seen_at=row.last_seen_at,
            deleted_at=row.deleted_at,
        )
