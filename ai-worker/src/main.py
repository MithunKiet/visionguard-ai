from src.config.logging_config import configure_logging

import asyncio
import platform
import structlog
import httpx
from src.config.settings import settings
from src.config.zone_sync import ZoneConfigSync
from src.config.assignment_cache import refresh_assignments
from src.events.publisher import get_journal, init_publisher, close_publisher, publish
from src.health.metrics import camera_target_fps, start_metrics_server
from src.pipeline.batch_detector import BatchDetector
from src.pipeline.camera_worker import CameraWorker

log = structlog.get_logger()

_AUTH_HEADERS = {
    "X-Worker-Key": settings.WORKER_API_KEY,
    "X-Enterprise-Id": settings.ENTERPRISE_ID,
}


async def register_worker() -> None:
    """Register / heartbeat with the backend so it exists before we ask for cameras."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.BACKEND_API_URL}/api/v1/workers/heartbeat",
            headers=_AUTH_HEADERS,
            json={
                "worker_id": settings.WORKER_ID,
                "hostname": platform.node(),
                "model_version": settings.YOLO_MODEL_PATH,
                "gpu_available": settings.USE_GPU,
            },
            timeout=10.0,
        )
        resp.raise_for_status()


async def fetch_assigned_cameras() -> list[dict]:
    """Pull camera assignments from Backend API on startup (AI Worker rule #3)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.BACKEND_API_URL}/api/v1/workers/{settings.WORKER_ID}/cameras",
            headers=_AUTH_HEADERS,
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["data"]


async def send_heartbeat() -> None:
    """AI Worker rule #11: heartbeat every 30 seconds, HTTP + event for observability.

    Both calls are independently guarded — a transient RabbitMQ hiccup here
    must not propagate out of this task, since it's gathered alongside every
    CameraWorker task in main(); an unhandled exception here would otherwise
    take down the whole process (all cameras on this worker), not just the
    heartbeat."""
    while True:
        await asyncio.sleep(30)
        try:
            await register_worker()
        except Exception as e:
            log.warning("ai_worker.heartbeat_failed", error_type=type(e).__name__)
        try:
            await publish("events.worker_heartbeat", {
                "event": "worker_heartbeat",
                "worker_id": settings.WORKER_ID,
            })
        except Exception as e:
            log.warning("ai_worker.heartbeat_publish_failed", error_type=type(e).__name__)


async def reconcile_cameras(workers: list, tasks: dict, detector, cameras: list) -> None:
    """Reconcile authoritative assignments, including missed config events."""
    assigned = {camera["camera_id"]: camera for camera in cameras}
    for worker in list(workers):
        camera = assigned.get(worker.camera_id)
        task = tasks[worker.camera_id]
        if camera is None or camera["rtsp_url"] != worker.rtsp_url or task.done():
            camera_target_fps.labels(camera_id=worker.camera_id).set(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            tasks.pop(worker.camera_id)
            workers.remove(worker)
    existing = {worker.camera_id: worker for worker in workers}
    for camera_id, camera in assigned.items():
        config = camera.get("zone_config") or {}
        overrides = camera.get("ppe_overrides") or {}
        if camera_id in existing:
            worker = existing[camera_id]
            normalized = worker._normalize_config(config)
            if normalized != worker.zone_config or overrides != worker.ppe_overrides:
                worker.ppe_overrides = overrides
                worker.apply_zone_config(config)
            worker.set_active(camera.get("status") != "Inactive")
        else:
            worker = CameraWorker(camera_id=camera_id, rtsp_url=camera["rtsp_url"],
                zone_config=config, ppe_overrides=overrides, enterprise_id=camera["enterprise_id"],
                factory_id=camera["factory_id"], zone_id=camera["zone_id"], detector=detector,
                active=camera.get("status") != "Inactive")
            workers.append(worker)
            tasks[camera_id] = asyncio.create_task(worker.run())


async def main() -> None:
    log.info("ai_worker.starting", worker_id=settings.WORKER_ID)
    start_metrics_server(settings.METRICS_PORT)
    await init_publisher()
    detector = None
    tasks = {}
    workers = []
    config_sync = ZoneConfigSync(workers, invalidate_cache=lambda: asyncio.to_thread(get_journal().clear_cache))
    heartbeat = None
    try:
        detector = BatchDetector()
        detector.start()
        heartbeat = asyncio.create_task(send_heartbeat())
        await config_sync.start()
        while True:
            try:
                cameras = await refresh_assignments(get_journal(), register_worker, fetch_assigned_cameras)
            except Exception as error:
                log.error("ai_worker.reconciliation_failed", error_type=type(error).__name__)
                cameras = []  # Corrupt/unreadable state cannot extend old authorization.
            await reconcile_cameras(workers, tasks, detector, cameras)
            await asyncio.sleep(30)
    finally:
        if heartbeat:
            heartbeat.cancel()
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*([heartbeat] if heartbeat else []), *tasks.values(), return_exceptions=True)
        if detector:
            await detector.stop()
        for worker in workers:
            camera_target_fps.labels(camera_id=worker.camera_id).set(0)
        await config_sync.stop()
        await close_publisher()
        log.info("ai_worker.stopped")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
