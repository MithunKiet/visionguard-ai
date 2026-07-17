"""
CameraService — CRUD, RTSP health check, worker assignment.
"""
import os
import structlog

from src.core.exceptions import NotFoundException
from src.modules.camera.domain.entities import CameraEntity
from src.modules.camera.infrastructure.repositories import CameraRepository
from src.modules.worker.infrastructure.repositories import WorkerRepository
from src.shared.security.scope import ScopeFilter

log = structlog.get_logger()

# Zone-level fallback used only if a camera's zone somehow has no config row
# (shouldn't happen — every zone gets one on creation — but keeps this
# resolution defensive rather than crashing on a response).
_DEFAULT_ZONE_PPE = ["helmet", "vest"]


class CameraService:

    def __init__(self, camera_repo: CameraRepository, worker_repo: WorkerRepository):
        self._cameras = camera_repo
        self._workers = worker_repo

    # ── List / Get ─────────────────────────────────────────────────────────

    async def list_cameras(
        self,
        enterprise_id: str,
        factory_id: str | None = None,
        zone_id: str | None = None,
        scope: ScopeFilter | None = None,
    ) -> list[CameraEntity]:
        return await self._cameras.list(enterprise_id, factory_id, zone_id, scope)

    async def get_camera(
        self, camera_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> CameraEntity:
        camera = await self._cameras.get_by_id(camera_id, enterprise_id, scope)
        if not camera:
            raise NotFoundException("Camera", str(camera_id))
        return camera

    # ── Create ─────────────────────────────────────────────────────────────

    async def create_camera(
        self,
        enterprise_id: str,
        zone_id: str,
        name: str,
        code: str,
        rtsp_url: str,
        db,
        camera_type: str = "Fixed",
        position_desc: str | None = None,
        fps: float | None = None,
        ppe_overrides: dict[str, bool] | None = None,
    ) -> CameraEntity:
        # factory_id is derived from the zone, never taken from the caller —
        # a camera's factory must always match its zone's, so there's no
        # independent value to trust or cross-validate here.
        from sqlalchemy import select
        from src.shared.database.models import Enterprise, Factory, Zone
        from src.shared.database.pid import to_pk, to_public_id

        ent_pk = await to_pk(db, Enterprise, enterprise_id)
        zone = (await db.execute(
            select(Zone).where(Zone.public_id == zone_id, Zone.enterprise_id == ent_pk)
        )).scalar_one_or_none()
        if not zone:
            raise NotFoundException("Zone", str(zone_id))

        factory_public_id = await to_public_id(db, Factory, zone.factory_id)

        entity = CameraEntity(
            enterprise_id=enterprise_id,
            factory_id=factory_public_id,
            zone_id=zone_id,
            name=name,
            code=code,
            rtsp_url=rtsp_url,
            camera_type=camera_type,
            position_desc=position_desc,
            fps=fps,
            status="Active",
            ppe_overrides={k: v for k, v in (ppe_overrides or {}).items() if v is not None},
        )
        camera = await self._cameras.create(entity)

        # Auto-assign to least-loaded worker
        await self._assign_worker_round_robin(camera)

        log.info("camera.created", camera_id=str(camera.id), name=name)
        return camera

    # ── Update ─────────────────────────────────────────────────────────────

    async def update_camera(
        self,
        camera_id: str,
        enterprise_id: str,
        scope: ScopeFilter | None = None,
        **fields,
    ) -> CameraEntity:
        camera = await self.get_camera(camera_id, enterprise_id, scope)

        # ppe_overrides is a partial patch merged into the existing dict —
        # a code omitted from the patch is left untouched, and a code mapped
        # to None clears that override (reverts to inheriting the zone's
        # setting), rather than the whole-field replace the other fields get.
        ppe_patch = fields.pop("ppe_overrides", None)
        if ppe_patch is not None:
            merged = dict(camera.ppe_overrides)
            for code, value in ppe_patch.items():
                if value is None:
                    merged.pop(code, None)
                else:
                    merged[code] = value
            camera.ppe_overrides = merged

        for key, val in fields.items():
            if val is not None and hasattr(camera, key):
                setattr(camera, key, val)
        return await self._cameras.update(camera)

    # ── Manual on/off toggle ────────────────────────────────────────────────

    async def set_active(
        self, camera_id: str, enterprise_id: str, active: bool, scope: ScopeFilter | None = None,
    ) -> CameraEntity:
        """Turns the camera on/off from the operator's point of view — the
        assigned AI worker keeps reading the RTSP stream (so it reconnects
        instantly if turned back on) but skips all detection work while off,
        applied live via config_events, no worker restart needed."""
        camera = await self.get_camera(camera_id, enterprise_id, scope)
        new_status = "Active" if active else "Inactive"
        await self._cameras.set_status(camera_id, new_status)
        camera.status = new_status

        from src.shared.messaging.publisher import publish_config_event
        await publish_config_event("config.camera_status_changed", {
            "event": "camera_status_changed",
            "camera_id": str(camera_id),
            "enterprise_id": str(enterprise_id),
            "status": new_status,
        })
        log.info("camera.status_changed", camera_id=str(camera_id), status=new_status)
        return camera

    # ── Mandatory PPE resolution ────────────────────────────────────────────

    @staticmethod
    def _compute_enforced(zone_required_ppe: list[str] | None, ppe_overrides: dict) -> list[str]:
        """Pure computation, no DB access — a code present in the camera's
        ppe_overrides wins over its zone's required_ppe_types for that code;
        codes not overridden fall back to the zone's list."""
        zone_required = set(zone_required_ppe or _DEFAULT_ZONE_PPE)
        overrides = ppe_overrides or {}
        enforced = (zone_required - {c for c, v in overrides.items() if v is False}) | \
                   {c for c, v in overrides.items() if v is True}
        return sorted(enforced)

    async def resolve_enforced_ppe(self, camera: CameraEntity, db) -> list[str]:
        """Single-camera version — used by create/get/update/status endpoints
        (N=1, a one-off query is fine there). List endpoints use
        resolve_enforced_ppe_batch below instead — see its docstring."""
        from sqlalchemy import select
        from src.shared.database.models import Zone, ZoneConfig
        from src.shared.database.pid import to_pk

        zone_pk = await to_pk(db, Zone, camera.zone_id)
        config = (await db.execute(
            select(ZoneConfig).where(ZoneConfig.zone_id == zone_pk)
        )).scalar_one_or_none()
        return self._compute_enforced(config.required_ppe_types if config else None, camera.ppe_overrides)

    async def resolve_enforced_ppe_batch(self, cameras: list[CameraEntity], db) -> dict[str, list[str]]:
        """Batched version for list endpoints — resolves every camera's zone
        config in 2 queries total (zone public_id -> pk, then zone configs),
        instead of 2 queries PER camera (an N+1 that scales with page size).
        Returns {camera.id (public_id): enforced_ppe_list}."""
        from sqlalchemy import select
        from src.shared.database.models import Zone, ZoneConfig

        zone_ids = list({c.zone_id for c in cameras})
        if not zone_ids:
            return {}

        zone_rows = (await db.execute(
            select(Zone.public_id, Zone.id).where(Zone.public_id.in_(zone_ids))
        )).all()
        zone_pk_by_public_id = dict(zone_rows)

        config_rows = (await db.execute(
            select(ZoneConfig.zone_id, ZoneConfig.required_ppe_types)
            .where(ZoneConfig.zone_id.in_(zone_pk_by_public_id.values()))
        )).all()
        required_ppe_by_zone_pk = dict(config_rows)

        result = {}
        for camera in cameras:
            zone_pk = zone_pk_by_public_id.get(camera.zone_id)
            zone_required = required_ppe_by_zone_pk.get(zone_pk)
            result[camera.id] = self._compute_enforced(zone_required, camera.ppe_overrides)
        return result

    # ── Delete ─────────────────────────────────────────────────────────────

    async def delete_camera(
        self, camera_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> None:
        await self.get_camera(camera_id, enterprise_id, scope)
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
                # Forces TCP instead of FFmpeg's default UDP for RTSP — many
                # corporate/WiFi networks drop the dynamically-negotiated
                # RTP/UDP ports RTSP-over-UDP needs, silently failing the
                # connection (see ai-worker/src/pipeline/frame_reader.py for
                # the same fix on the actual detection pipeline).
                os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
                start = time.monotonic()
                cap = cv2.VideoCapture(rtsp_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, _ = cap.read()
                latency_ms = int((time.monotonic() - start) * 1000)
                cap.release()
                return ok, latency_ms
            except Exception:
                return False, 0

        ok, latency_ms = await asyncio.get_event_loop().run_in_executor(None, _probe)
        return {
            "reachable": ok,
            "latency_ms": latency_ms,
            "rtsp_url": rtsp_url,
            "status": "Online" if ok else "Offline",
        }

    # ── Health ─────────────────────────────────────────────────────────────

    async def get_camera_health(
        self, camera_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> dict:
        camera = await self.get_camera(camera_id, enterprise_id, scope)
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
            worker_pk = await self._workers.get_internal_id(w.id)
            count = await self._cameras.count_by_worker(worker_pk)
            counts.append((count, w))

        counts.sort(key=lambda x: x[0])
        chosen = counts[0][1]
        await self._cameras.assign_worker(camera.id, chosen.id)
        log.info("camera.worker_assigned", camera_id=str(camera.id), worker_id=str(chosen.id))
