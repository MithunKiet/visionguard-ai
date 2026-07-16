from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.camera.domain.entities import CameraEntity
from src.modules.camera.domain.repositories import ICameraRepository
from src.shared.database.models import AIWorker, Camera, Enterprise, Factory, Zone
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_zone_scope

# Camera has 3 FK-shaped fields (worker_id nullable) — resolving each with a
# separate to_public_id query per row is N+1 on list() (a page of cameras =
# 3-4x round trips per row). Join once instead — see _to_entity_from_row.
_JOINED_COLUMNS = (Camera, Factory.public_id, Zone.public_id, AIWorker.public_id)


class CameraRepository(ICameraRepository):

    def __init__(self, db: AsyncSession):
        self._db = db

    async def list(
        self,
        enterprise_id: str,
        factory_id: str | None = None,
        zone_id: str | None = None,
        scope: ScopeFilter | None = None,
    ) -> list[CameraEntity]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(*_JOINED_COLUMNS)
            .join(Factory, Factory.id == Camera.factory_id)
            .join(Zone, Zone.id == Camera.zone_id)
            .outerjoin(AIWorker, AIWorker.id == Camera.worker_id)
            .where(
                Camera.enterprise_id == ent_pk,
                Camera.deleted_at.is_(None),
            )
        )
        if factory_id:
            q = q.where(Camera.factory_id == await to_pk(self._db, Factory, factory_id))
        if zone_id:
            q = q.where(Camera.zone_id == await to_pk(self._db, Zone, zone_id))
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Camera.factory_id, Camera.zone_id)
        rows = (await self._db.execute(q.order_by(Camera.name))).all()
        return [self._to_entity_from_row(*row, enterprise_id) for row in rows]

    async def get_by_id(
        self, camera_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> CameraEntity | None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(Camera).where(
            Camera.public_id == camera_id,
            Camera.enterprise_id == ent_pk,
            Camera.deleted_at.is_(None),
        )
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Camera.factory_id, Camera.zone_id)
        result = await self._db.execute(q)
        row = result.scalar_one_or_none()
        return await self._to_entity(row) if row else None

    async def create(self, entity: CameraEntity) -> CameraEntity:
        row = Camera(
            enterprise_id=await to_pk(self._db, Enterprise, entity.enterprise_id),
            factory_id=await to_pk(self._db, Factory, entity.factory_id),
            zone_id=await to_pk(self._db, Zone, entity.zone_id),
            name=entity.name,
            code=entity.code,
            rtsp_url=entity.rtsp_url,
            camera_type=entity.camera_type,
            position_desc=entity.position_desc,
            status=entity.status,
            fps=entity.fps,
            ppe_overrides=entity.ppe_overrides,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return await self._to_entity(row)

    async def update(self, entity: CameraEntity) -> CameraEntity:
        await self._db.execute(
            update(Camera).where(Camera.public_id == entity.id).values(
                name=entity.name,
                rtsp_url=entity.rtsp_url,
                camera_type=entity.camera_type,
                position_desc=entity.position_desc,
                status=entity.status,
                fps=entity.fps,
                in_maintenance=entity.in_maintenance,
                maintenance_until=entity.maintenance_until,
                ppe_overrides=entity.ppe_overrides,
                updated_at=datetime.now(timezone.utc),
                version=Camera.version + 1,
            )
        )
        await self._db.commit()
        return entity

    async def set_status(self, camera_id: str, status: str) -> None:
        await self._db.execute(
            update(Camera).where(Camera.public_id == camera_id).values(
                status=status,
                last_seen_at=datetime.now(timezone.utc),
            )
        )
        await self._db.commit()

    async def delete(self, camera_id: str, enterprise_id: str) -> None:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        await self._db.execute(
            update(Camera).where(
                Camera.public_id == camera_id,
                Camera.enterprise_id == ent_pk,
            ).values(deleted_at=datetime.now(timezone.utc))
        )
        await self._db.commit()

    async def assign_worker(self, camera_id: str, worker_id: str | None) -> None:
        worker_pk = await to_pk(self._db, AIWorker, worker_id) if worker_id else None
        await self._db.execute(
            update(Camera).where(Camera.public_id == camera_id).values(worker_id=worker_pk)
        )
        await self._db.commit()

    async def list_by_worker(self, worker_id: int) -> list[CameraEntity]:
        result = await self._db.execute(
            select(Camera).where(
                Camera.worker_id == worker_id,
                Camera.deleted_at.is_(None),
            )
        )
        return [await self._to_entity(r) for r in result.scalars()]

    async def count_by_worker(self, worker_id: int) -> int:
        result = await self._db.execute(
            select(func.count()).where(
                Camera.worker_id == worker_id,
                Camera.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def _to_entity(self, row: Camera) -> CameraEntity:
        """Single-row path (create/get_by_id/etc.) — list() above uses a
        joined query instead to avoid paying this per row; see _JOINED_COLUMNS."""
        return CameraEntity(
            id=row.public_id,
            enterprise_id=await to_public_id(self._db, Enterprise, row.enterprise_id),
            factory_id=await to_public_id(self._db, Factory, row.factory_id),
            zone_id=await to_public_id(self._db, Zone, row.zone_id),
            worker_id=await to_public_id(self._db, AIWorker, row.worker_id),
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
            ppe_overrides=row.ppe_overrides or {},
        )

    @staticmethod
    def _to_entity_from_row(
        c: Camera, factory_public_id: str, zone_public_id: str,
        worker_public_id: str | None, enterprise_id: str,
    ) -> CameraEntity:
        return CameraEntity(
            id=c.public_id,
            enterprise_id=enterprise_id,
            factory_id=factory_public_id,
            zone_id=zone_public_id,
            worker_id=worker_public_id,
            name=c.name,
            code=c.code,
            rtsp_url=c.rtsp_url,
            camera_type=c.camera_type,
            position_desc=c.position_desc,
            status=c.status,
            fps=c.fps,
            in_maintenance=c.in_maintenance,
            maintenance_until=c.maintenance_until,
            last_seen_at=c.last_seen_at,
            deleted_at=c.deleted_at,
            ppe_overrides=c.ppe_overrides or {},
        )
