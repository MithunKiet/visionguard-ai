import asyncio
import platform
import structlog
import httpx
from src.config.settings import settings
from src.events.publisher import init_publisher, close_publisher, publish
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
    """AI Worker rule #11: heartbeat every 30 seconds, HTTP + event for observability."""
    while True:
        await asyncio.sleep(30)
        try:
            await register_worker()
        except Exception as e:
            log.warning("ai_worker.heartbeat_failed", error=str(e))
        await publish("events.worker_heartbeat", {
            "event": "worker_heartbeat",
            "worker_id": settings.WORKER_ID,
        })


async def main() -> None:
    log.info("ai_worker.starting", worker_id=settings.WORKER_ID)

    await init_publisher()
    await register_worker()

    cameras = await fetch_assigned_cameras()
    log.info("ai_worker.cameras_loaded", count=len(cameras))

    tasks = []

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
        )
        tasks.append(asyncio.create_task(worker.run()))

    if not cameras:
        log.warning("ai_worker.no_cameras_assigned", worker_id=settings.WORKER_ID)

    try:
        await asyncio.gather(*tasks)
    finally:
        await close_publisher()
        log.info("ai_worker.stopped")


if __name__ == "__main__":
    asyncio.run(main())
