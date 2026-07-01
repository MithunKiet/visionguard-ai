"""
CameraService — CRUD, RTSP health check, worker assignment.
"""
import uuid
from uuid import UUID

import structlog

from src.core.exceptions import NotFoundException, VisionGuardException
from src.modules.camera.domain.entities import CameraEntity
from src.modules.camera.infrastructure.repositories import CameraRepository
from src.modules.worker.infrastructure.repositories import WorkerRepository

log = structlog.get_logger()


class CameraService:

    def __init__(self, camera_repo: CameraRepository, worker_repo: WorkerRepository):
        self._cameras = camera_repo
        self._workers = worker_repo

    # ── List / Get ─────────────────────────────────────────────────────────

    async def list_cameras(
        self,
        enterprise_id: UUID,
        factory_id: UUID | None = None,
        zone_id: UUID | None = None,
    ) -> list[CameraEntity]:
        return await self._cameras.list(enterprise_id, factory_id, zone_id)

    async def get_camera(self, camera_id: UUID, enterprise_id: UUID) -> CameraEntity:
        camera = await self._cameras.get_by_id(camera_id, enterprise_id)
        if not camera:
            raise NotFoundException("Camera", str(camera_id))
        return camera

    # ── Create ─────────────────────────────────────────────────────────────

    async def create_camera(
        self,
        enterprise_id: UUID,
        factory_id: UUID,
        zone_id: UUID,
        name: str,
        code: str,
        rtsp_url: str,
        camera_type: str = "Fixed",
        position_desc: str | None = None,
        fps: float | None = None,
    ) -> CameraEntity:
        entity = CameraEntity(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            factory_id=factory_id,
            zone_id=zone_id,
            name=name,
            code=code,
            rtsp_url=rtsp_url,
            camera_type=camera_type,
            position_desc=position_desc,
            fps=fps,
            status="Active",
        )
        camera = await self._cameras.create(entity)

        # Auto-assign to least-loaded worker
        await self._assign_worker_round_robin(camera)

        log.info("camera.created", camera_id=str(camera.id), name=name)
        return camera

    # ── Update ─────────────────────────────────────────────────────────────

    async def update_camera(
        self,
        camera_id: UUID,
        enterprise_id: UUID,
        **fields,
    ) -> CameraEntity:
        camera = await self.get_camera(camera_id, enterprise_id)
        for key, val in fields.items():
            if val is not None and hasattr(camera, key):
                setattr(camera, key, val)
        return await self._cameras.update(camera)

    # ── Delete ─────────────────────────────────────────────────────────────

    async def delete_camera(self, camera_id: UUID, enterprise_id: UUID) -> None:
        await self.get_camera(camera_id, enterprise_id)
        await self._cameras.delete(camera_id, enterprise_id)
        log.info("camera.deleted", camera_id=str(camera_id))

    # ── RTSP Health Check ──────────────────────────────────────────────────

    async def test_rtsp_connection(self, rtsp_url: str) -> dict:
        """
        Attempt to open the RTSP stream with OpenCV and read one frame.
        Returns status + latency_ms.
        """
        import asyncio
        import time

        def _probe():
            try:
                import cv2
                start = time.monotonic()
                cap = cv2.VideoCapture(rtsp_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, _ = cap.read()
                latency_ms = int((time.monotonic() - start) * 1000)
                cap.release()
                return ok, latency_ms
            except Exception as exc:
                return False, 0

        ok, latency_ms = await asyncio.get_event_loop().run_in_executor(None, _probe)
        return {
            "reachable": ok,
            "latency_ms": latency_ms,
            "rtsp_url": rtsp_url,
            "status": "Online" if ok else "Offline",
        }

    # ── Health ─────────────────────────────────────────────────────────────

    async def get_camera_health(self, camera_id: UUID, enterprise_id: UUID) -> dict:
        camera = await self.get_camera(camera_id, enterprise_id)
        probe = await self.test_rtsp_connection(camera.rtsp_url)
        return {
            "camera_id": str(camera_id),
            "name": camera.name,
            "status": camera.status,
            "in_maintenance": camera.in_maintenance,
            "last_seen_at": camera.last_seen_at.isoformat() if camera.last_seen_at else None,
            "rtsp_reachable": probe["reachable"],
            "rtsp_latency_ms": probe["latency_ms"],
        }

    # ── Worker Assignment (round-robin) ────────────────────────────────────

    async def _assign_worker_round_robin(self, camera: CameraEntity) -> None:
        workers = await self._workers.list_active(camera.enterprise_id)
        if not workers:
            log.warning("camera.no_workers_available", camera_id=str(camera.id))
            return

        # Pick worker with fewest cameras
        counts = []
        for w in workers:
            count = await self._cameras.count_by_worker(w.id)
            counts.append((count, w))

        counts.sort(key=lambda x: x[0])
        chosen = counts[0][1]
        await self._cameras.assign_worker(camera.id, chosen.id)
        log.info("camera.worker_assigned", camera_id=str(camera.id), worker_id=str(chosen.id))
