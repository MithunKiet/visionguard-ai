"""
WorkerService — heartbeat, registry, camera-config dispatch.
"""
import structlog

from src.modules.worker.domain.entities import WorkerEntity
from src.modules.worker.infrastructure.repositories import WorkerRepository

log = structlog.get_logger()

_DEFAULT_ZONE_PPE = ["helmet", "vest"]


def _resolve_ppe_required(cam, config) -> list[str]:
    """Effective mandatory-PPE list sent to the AI worker: a code in the
    camera's ppe_overrides wins over its zone's required_ppe_types for that
    code; codes not overridden fall back to the zone's list (or the
    platform default if the zone somehow has no config row)."""
    zone_required = set((config.required_ppe_types if config else _DEFAULT_ZONE_PPE) or [])
    overrides = getattr(cam, "ppe_overrides", None) or {}

    enforced = (zone_required - {c for c, v in overrides.items() if v is False}) | \
               {c for c, v in overrides.items() if v is True}
    return sorted(enforced)


class WorkerService:

    def __init__(self, repo: WorkerRepository):
        self._repo = repo

    async def heartbeat(
        self,
        enterprise_id: str,
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

    async def list_workers(self, enterprise_id: str) -> list[WorkerEntity]:
        return await self._repo.list_all(enterprise_id)

    async def get_worker_cameras_by_business_id(self, worker_id: str, db, enterprise_id: str | None = None) -> list:
        """
        Resolve the AI Worker's business id (e.g. "worker-1") to its internal
        integer id, then return cameras + zone configs assigned to it.
        """
        worker_db_id = await self._repo.get_internal_id_by_worker_id(worker_id, enterprise_id)
        if not worker_db_id:
            return []
        return await self.get_worker_cameras(worker_db_id, db)

    async def get_worker_cameras(self, worker_db_id: int, db) -> list:
        """
        Return cameras + zone configs assigned to this worker.
        Used by the AI Worker on startup to know what to watch.
        """
        from src.modules.camera.infrastructure.repositories import CameraRepository
        from src.shared.database.models import Zone, ZoneConfig
        from src.shared.database.pid import to_pk
        from sqlalchemy import select

        cam_repo = CameraRepository(db)
        cameras = await cam_repo.list_by_worker(worker_db_id)

        result = []
        for cam in cameras:
            # Fetch zone config for this camera's zone — cam.zone_id is the
            # zone's public_id; ZoneConfig.zone_id is the internal FK, so
            # resolve before querying.
            zone_pk = await to_pk(db, Zone, cam.zone_id)
            config_result = await db.execute(
                select(ZoneConfig).where(ZoneConfig.zone_id == zone_pk)
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
                "status": cam.status,
                "in_maintenance": cam.in_maintenance,
                "zone_config": {
                    "person_threshold": config.person_threshold if config else 0.70,
                    "helmet_threshold": config.helmet_threshold if config else 0.75,
                    "vest_threshold": config.vest_threshold if config else 0.75,
                    "gloves_threshold": config.gloves_threshold if config else 0.70,
                    "shoes_threshold": config.shoes_threshold if config else 0.70,
                    "mask_threshold": config.mask_threshold if config else 0.75,
                    "frame_sample_fps": config.frame_sample_fps if config else 2,
                    "ppe_required": _resolve_ppe_required(cam, config),
                    "cooldown_seconds": config.cooldown_seconds if config else 120,
                    "required_consecutive_frames": config.required_consecutive_frames if config else 3,
                    "low_confidence_floor": config.low_confidence_floor if config else 0.40,
                    "max_occupancy": config.max_occupancy if config else None,
                    "config_version": config.version if config else 1,
                } if config else None,
            })
        return result
