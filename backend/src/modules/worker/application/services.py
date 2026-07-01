"""
WorkerService — heartbeat, registry, camera-config dispatch.
"""
from uuid import UUID

import structlog

from src.modules.worker.domain.entities import WorkerEntity
from src.modules.worker.infrastructure.repositories import WorkerRepository

log = structlog.get_logger()


class WorkerService:

    def __init__(self, repo: WorkerRepository):
        self._repo = repo

    async def heartbeat(
        self,
        enterprise_id: UUID,
        worker_id: str,
        hostname: str | None,
        model_version: str | None,
        gpu_available: bool,
    ) -> WorkerEntity:
        worker = await self._repo.upsert_heartbeat(
            enterprise_id=enterprise_id,
            worker_id=worker_id,
            hostname=hostname,
            model_version=model_version,
            gpu_available=gpu_available,
        )
        log.debug("worker.heartbeat", worker_id=worker_id)
        return worker

    async def list_workers(self, enterprise_id: UUID) -> list[WorkerEntity]:
        return await self._repo.list_all(enterprise_id)

    async def get_worker_cameras_by_business_id(self, worker_id: str, db) -> list:
        """
        Resolve the AI Worker's business id (e.g. "worker-1") to its DB row,
        then return cameras + zone configs assigned to it.
        """
        worker = await self._repo.get_by_worker_id(worker_id)
        if not worker:
            return []
        return await self.get_worker_cameras(worker.id, db)

    async def get_worker_cameras(self, worker_db_id: UUID, db) -> list:
        """
        Return cameras + zone configs assigned to this worker.
        Used by the AI Worker on startup to know what to watch.
        """
        from src.modules.camera.infrastructure.repositories import CameraRepository
        from src.shared.database.models import ZoneConfig
        from sqlalchemy import select

        cam_repo = CameraRepository(db)
        cameras = await cam_repo.list_by_worker(worker_db_id)

        result = []
        for cam in cameras:
            # Fetch zone config for this camera's zone
            config_result = await db.execute(
                select(ZoneConfig).where(ZoneConfig.zone_id == cam.zone_id)
            )
            config = config_result.scalar_one_or_none()

            result.append({
                "id": str(cam.id),
                "camera_id": str(cam.id),
                "camera_code": cam.code,
                "rtsp_url": cam.rtsp_url,
                "enterprise_id": str(cam.enterprise_id),
                "factory_id": str(cam.factory_id),
                "zone_id": str(cam.zone_id),
                "in_maintenance": cam.in_maintenance,
                "zone_config": {
                    "person_threshold": config.person_threshold if config else 0.70,
                    "helmet_threshold": config.helmet_threshold if config else 0.75,
                    "vest_threshold": config.vest_threshold if config else 0.75,
                    "gloves_threshold": config.gloves_threshold if config else 0.70,
                    "shoes_threshold": config.shoes_threshold if config else 0.70,
                    "mask_threshold": config.mask_threshold if config else 0.75,
                    "frame_sample_fps": config.frame_sample_fps if config else 2,
                    "ppe_required": config.ppe_required if config else ["helmet", "vest"],
                    "cooldown_seconds": config.cooldown_seconds if config else 120,
                    "max_occupancy": config.max_occupancy if config else None,
                    "config_version": config.version if config else 1,
                } if config else None,
            })
        return result
