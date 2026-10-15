"""Tenant-scoped scheduling with a PostgreSQL lock shared by all API processes."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.core.exceptions import NotFoundException, VisionGuardException
from src.shared.database.models import AIWorker, Camera, Enterprise, Factory, Zone, ZoneConfig


class WorkerSchedulingRepository:
    def __init__(self, db):
        self._db = db

    async def _lock_enterprise(self, enterprise_id: str) -> int:
        # FOR NO KEY UPDATE serializes policy/admission transactions without
        # blocking unrelated inserts taking FK KEY SHARE locks on the tenant.
        ent_pk = await self._db.scalar(select(Enterprise.id).where(
            Enterprise.public_id == enterprise_id, Enterprise.deleted_at.is_(None),
        ).with_for_update(key_share=True))
        if ent_pk is None:
            raise NotFoundException("Enterprise", enterprise_id)
        return ent_pk

    async def configure(self, worker_id: str, enterprise_id: str, factory_id: str, max_cameras: int, actor: str):
        ent_pk = await self._lock_enterprise(enterprise_id)
        worker = await self._db.scalar(select(AIWorker).where(
            AIWorker.public_id == worker_id, AIWorker.enterprise_id == ent_pk,
            AIWorker.deleted_at.is_(None),
        ).execution_options(populate_existing=True))
        if worker is None:
            raise NotFoundException("Worker", worker_id)
        factory = await self._db.scalar(select(Factory).where(
            Factory.public_id == factory_id, Factory.enterprise_id == ent_pk,
            Factory.deleted_at.is_(None), Factory.is_active.is_(True), Factory.status == "Active",
        ))
        if factory is None:
            raise NotFoundException("Factory", factory_id)
        if not 1 <= max_cameras <= 10000:
            raise VisionGuardException("INVALID_CAPACITY", "Camera limit must be between 1 and 10000", 422)
        assignments = (await self._db.execute(select(Camera.factory_id, Camera.enterprise_id).where(
            Camera.worker_id == worker.id, Camera.deleted_at.is_(None),
        ))).all()
        if len(assignments) > max_cameras or any(f != factory.id or e != ent_pk for f, e in assignments):
            raise VisionGuardException("WORKER_POLICY_CONFLICT",
                "Existing assignments exceed this limit or belong to another factory; reconcile them during a fenced maintenance window", 409)
        worker.factory_id = factory.id
        worker.max_cameras = max_cameras
        worker.updated_by = actor
        worker.updated_at = datetime.now(timezone.utc)
        await self._db.commit()

    async def admit_pending(self, enterprise_id: str, *, camera_id: str | None = None,
                            worker_public_id: str | None = None) -> dict[str, str]:
        """Assign only unowned cameras. Never steal a stale worker's assignments.

        Callers either request one camera at creation or backfill one worker's
        factory on a poll. Counts include inactive cameras: their readers remain
        connected. At most 100 pending cameras are admitted per transaction.
        """
        ent_pk = await self._lock_enterprise(enterprise_id)
        pending = select(Camera).join(Zone, Zone.id == Camera.zone_id).where(
            Camera.enterprise_id == ent_pk, Camera.worker_id.is_(None),
            Camera.deleted_at.is_(None), Camera.is_active.is_(True),
            Zone.enterprise_id == ent_pk, Zone.factory_id == Camera.factory_id,
            Zone.deleted_at.is_(None), Zone.is_active.is_(True), Zone.status == "Active",
        )
        if camera_id is not None:
            camera = await self._db.scalar(select(Camera).where(
                Camera.public_id == camera_id, Camera.enterprise_id == ent_pk,
                Camera.deleted_at.is_(None),
            ))
            if camera is None or camera.worker_id is not None:
                await self._db.commit()
                return {}
            factory_pk = camera.factory_id
            pending = pending.where(Camera.id == camera.id)
        else:
            worker = await self._db.scalar(select(AIWorker).where(
                AIWorker.public_id == worker_public_id, AIWorker.enterprise_id == ent_pk,
                AIWorker.deleted_at.is_(None), AIWorker.is_active.is_(True),
            ).execution_options(populate_existing=True))
            if worker is None or worker.factory_id is None or worker.max_cameras < 1:
                await self._db.commit()
                return {}
            factory_pk = worker.factory_id
        workers = list((await self._db.scalars(select(AIWorker).join(Factory, Factory.id == AIWorker.factory_id).where(
            AIWorker.enterprise_id == ent_pk, AIWorker.factory_id == factory_pk,
            AIWorker.deleted_at.is_(None), AIWorker.is_active.is_(True),
            AIWorker.max_cameras > 0, AIWorker.status == "Online",
            AIWorker.last_heartbeat > datetime.now(timezone.utc) - timedelta(seconds=60),
            Factory.enterprise_id == ent_pk, Factory.deleted_at.is_(None), Factory.is_active.is_(True), Factory.status == "Active",
        ).order_by(AIWorker.id).execution_options(populate_existing=True))).all())
        if not workers:
            await self._db.commit()
            return {}
        counts = dict((await self._db.execute(select(Camera.worker_id, func.count()).where(
            Camera.worker_id.in_([w.id for w in workers]), Camera.deleted_at.is_(None),
        ).group_by(Camera.worker_id))).all())
        assignments = {}
        cameras = await self._db.scalars(pending.where(Camera.factory_id == factory_pk)
                                        .order_by(Camera.created_at, Camera.id).limit(100))
        for camera in cameras:
            eligible = [w for w in workers if counts.get(w.id, 0) < w.max_cameras]
            if not eligible:
                break
            chosen = min(eligible, key=lambda w: (counts.get(w.id, 0) / w.max_cameras, w.id))
            camera.worker_id = chosen.id
            counts[chosen.id] = counts.get(chosen.id, 0) + 1
            assignments[camera.public_id] = chosen.public_id
        await self._db.commit()
        return assignments

    async def assignment_rows(self, worker_pk: int):
        # One joined query replaces the previous six lookups per camera.
        return (await self._db.execute(select(
            Camera, Enterprise.public_id, Factory.public_id, Zone.public_id, ZoneConfig,
        ).join(AIWorker, AIWorker.id == Camera.worker_id)
          .join(Enterprise, Enterprise.id == Camera.enterprise_id)
          .join(Factory, Factory.id == Camera.factory_id)
          .join(Zone, Zone.id == Camera.zone_id)
          .outerjoin(ZoneConfig, (ZoneConfig.zone_id == Zone.id) & (ZoneConfig.enterprise_id == Camera.enterprise_id))
          .where(
              AIWorker.id == worker_pk, AIWorker.factory_id == Camera.factory_id,
              AIWorker.enterprise_id == Camera.enterprise_id, AIWorker.max_cameras > 0,
              AIWorker.deleted_at.is_(None), AIWorker.is_active.is_(True),
              Enterprise.deleted_at.is_(None), Camera.deleted_at.is_(None), Camera.is_active.is_(True),
              Factory.enterprise_id == Camera.enterprise_id, Factory.deleted_at.is_(None), Factory.is_active.is_(True), Factory.status == "Active",
              Zone.enterprise_id == Camera.enterprise_id, Zone.factory_id == Camera.factory_id,
              Zone.deleted_at.is_(None), Zone.is_active.is_(True), Zone.status == "Active",
          ).order_by(Camera.id))).all()
