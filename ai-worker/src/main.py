from src.config.logging_config import configure_logging

configure_logging()

import asyncio
import platform
import structlog
import httpx
from src.config.settings import settings
from src.config.zone_sync import ZoneConfigSync
from src.events.publisher import init_publisher, close_publisher, publish
from src.health.metrics import start_metrics_server
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
        return resp.json().get("data") or []


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
            log.warning("ai_worker.heartbeat_failed", error=str(e))
        try:
            await publish("events.worker_heartbeat", {
                "event": "worker_heartbeat",
                "worker_id": settings.WORKER_ID,
            })
        except Exception as e:
            log.warning("ai_worker.heartbeat_publish_failed", error=str(e))


async def main() -> None:
    log.info("ai_worker.starting", worker_id=settings.WORKER_ID)

    start_metrics_server(settings.METRICS_PORT)
    await init_publisher()
    await register_worker()

    cameras = await fetch_assigned_cameras()
    log.info("ai_worker.cameras_loaded", count=len(cameras))

    # One model loaded once per process, shared by every camera below —
    # each camera submits frames to it and inference runs in GPU-friendly
    # batches instead of one single-image call per camera.
    detector = BatchDetector()
    detector.start()

    tasks = []
    workers: list[CameraWorker] = []

    # Start heartbeat
    tasks.append(asyncio.create_task(send_heartbeat()))

    # Start one CameraWorker per assigned camera
    for cam in cameras:
        worker = CameraWorker(
            camera_id=cam["camera_id"],
            rtsp_url=cam["rtsp_url"],
            zone_config=cam.get("zone_config", {}),
            enterprise_id=cam["enterprise_id"],
            factory_id=cam["factory_id"],
            zone_id=cam["zone_id"],
            detector=detector,
            active=cam.get("status") != "Inactive",
        )
        workers.append(worker)
        tasks.append(asyncio.create_task(worker.run()))

    if not cameras:
        log.warning("ai_worker.no_cameras_assigned", worker_id=settings.WORKER_ID)

    # Zone config hot-reload — applies backend config pushes without restart
    config_sync = ZoneConfigSync(workers)
    await config_sync.start()

    try:
        # return_exceptions=True: one task's unhandled exception (heartbeat,
        # a CameraWorker that somehow escapes its own circuit breaker, etc.)
        # must not tear down every other camera on this worker — log it and
        # keep the rest of the process running instead of crashing whole-sale.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                log.error("ai_worker.task_failed", task=task.get_name(), error=str(result))
    finally:
        await config_sync.stop()
        await close_publisher()
        log.info("ai_worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
