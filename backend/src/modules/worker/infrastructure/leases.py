"""Database-clock leases. Heartbeats alone never renew camera authorization."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select

from src.core.exceptions import VisionGuardException
from src.modules.worker.infrastructure.scheduling import WorkerSchedulingRepository
from src.shared.database.models import AIWorker, Camera, CameraLease, Factory, Zone

log = structlog.get_logger()
LEASE_SECONDS = 90


class CameraLeaseRepository(WorkerSchedulingRepository):
    async def acquire(self, enterprise_id, worker_pk, session_id):
        session_id = str(UUID(session_id))
        ent_pk = await self._lock_enterprise(enterprise_id)
        # Use database wall time AFTER acquiring the serialization lock. SQL now()
        # is transaction-start time and could grant stale leases after lock waits.
        now = await self._db.scalar(select(func.clock_timestamp()))
        worker = await self._db.scalar(select(AIWorker).join(Factory, Factory.id == AIWorker.factory_id).where(
            AIWorker.id == worker_pk, AIWorker.enterprise_id == ent_pk,
            AIWorker.is_active.is_(True), AIWorker.deleted_at.is_(None),
            AIWorker.status == "Online", AIWorker.last_heartbeat > now - timedelta(seconds=60),
            AIWorker.max_cameras > 0, Factory.enterprise_id == ent_pk,
            Factory.is_active.is_(True), Factory.deleted_at.is_(None), Factory.status == "Active",
        ).execution_options(populate_existing=True))
        if worker is None:
            await self._db.commit()
            return {}
        # Lock all relevant camera rows in ID order, shared with event writes.
        # Legacy (generation zero) assignments are never automatically stolen.
        rows = (await self._db.execute(select(Camera, CameraLease).outerjoin(CameraLease,
            (CameraLease.camera_id == Camera.id) & (CameraLease.generation == Camera.assignment_generation))
            .join(Zone, Zone.id == Camera.zone_id).where(
                Camera.enterprise_id == ent_pk, Camera.factory_id == worker.factory_id,
                Camera.deleted_at.is_(None), Camera.is_active.is_(True),
                Zone.enterprise_id == ent_pk, Zone.factory_id == worker.factory_id,
                Zone.is_active.is_(True), Zone.deleted_at.is_(None), Zone.status == "Active",
            ).order_by(Camera.id).with_for_update(of=Camera)
            .execution_options(populate_existing=True))).all()
        now = await self._db.scalar(select(func.clock_timestamp()))
        count = await self._db.scalar(select(func.count()).select_from(Camera).where(
            Camera.worker_id == worker.id, Camera.deleted_at.is_(None)))
        grants = {}
        transferred = []
        for camera, lease in rows:
            if camera.assignment_generation > 0 and lease is None:
                raise VisionGuardException("LEASE_HISTORY_MISSING",
                    "Current camera ownership history is missing; restore it before scheduling", 503)
            owned = camera.worker_id == worker.id
            live = lease is not None and lease.expires_at > now
            if live:
                if not owned or lease.worker_id != worker.id:
                    continue
                if lease.session_id != session_id:
                    raise VisionGuardException("WORKER_SESSION_CONFLICT",
                        "Another process owns this worker's live camera lease; wait for expiry", 409)
            elif not owned:
                if camera.worker_id is not None and lease is None:
                    continue
                if count >= worker.max_cameras:
                    continue
                if lease is not None:
                    transferred.append(camera.public_id)
                camera.worker_id = worker.id
                count += 1
            if not live:
                camera.assignment_generation += 1
                lease = CameraLease(token=str(uuid4()), camera_id=camera.id,
                    generation=camera.assignment_generation, worker_id=worker.id,
                    session_id=session_id, started_at=now, expires_at=now)
                self._db.add(lease)
            lease.expires_at = now + timedelta(seconds=LEASE_SECONDS)
            grants[camera.public_id] = {"token": lease.token, "generation": lease.generation,
                "session_id": session_id, "server_time": now.isoformat(),
                "expires_at": lease.expires_at.isoformat(), "ttl_seconds": LEASE_SECONDS}
        await self._db.commit()
        for camera_id in transferred:
            log.info("camera.ownership_transferred", camera_id=camera_id, worker_id=worker.worker_id)
        return grants


async def fence_camera_event(db, body, *, historical=False):
    """Hold the camera row until the side-effect transaction commits.

    Historical incidents retain their original grant; live telemetry must use
    the current unexpired generation. Workers are trusted reporters, not an
    adversarial source of timestamps. Tokens must never be logged.
    """
    camera = await db.scalar(select(Camera).where(Camera.public_id == body["camera_id"])
        .with_for_update().execution_options(populate_existing=True))
    if camera is None:
        raise ValueError("Unknown event camera")
    if camera.assignment_generation == 0:
        return  # Upgrade compatibility only: these cameras cannot fail over.
    grant = body.get("camera_lease") or {}
    lease = await db.get(CameraLease, str(grant.get("token", "")))
    worker_id = await db.scalar(select(AIWorker.worker_id).where(AIWorker.id == lease.worker_id)) if lease else None
    if (lease is None or lease.camera_id != camera.id or lease.generation != grant.get("generation")
            or lease.session_id != grant.get("session_id") or worker_id != body.get("worker_id")):
        raise ValueError("Camera event ownership fence rejected")
    observed = datetime.fromisoformat(grant["observed_at"].replace("Z", "+00:00"))
    now = await db.scalar(select(func.clock_timestamp()))
    if observed.tzinfo is None or not lease.started_at <= observed < lease.expires_at or observed > now:
        raise ValueError("Camera event outside its authorized lease window")
    if not historical and (camera.assignment_generation != lease.generation
            or camera.worker_id != lease.worker_id or now >= lease.expires_at):
        raise ValueError("Stale camera telemetry rejected")
