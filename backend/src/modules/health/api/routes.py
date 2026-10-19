import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.settings import settings
from src.shared.cache.client import get_redis
from src.shared.database.session import SCHEMA_VERSION, engine
from src.shared.responses import ApiResponse
from src.shared.storage.minio_client import get_minio

router = APIRouter(tags=["Health"])


@router.get("/health/live")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    async def database():
        async with engine.connect() as connection:
            if await connection.scalar(text("SELECT version_num FROM alembic_version")) != SCHEMA_VERSION:
                raise RuntimeError("Migrations required")

    async def broker():
        from src.shared.messaging.consumer import _connection
        if _connection is None or _connection.is_closed or not _connection.connected.is_set():
            raise RuntimeError("Broker unavailable")

    async def storage():
        if not await asyncio.to_thread(get_minio().bucket_exists, settings.MINIO_BUCKET_SNAPSHOTS):
            raise RuntimeError("Snapshot bucket unavailable")

    async def cache():
        await get_redis().ping()

    async def notifications():
        from src.modules.notifications.application.outbox import delivery_worker
        if not delivery_worker.tasks or any(task.done() for task in delivery_worker.tasks):
            raise RuntimeError("Notification delivery worker unavailable")

    async def config_delivery():
        from src.modules.config.application.delivery import config_delivery_worker
        if config_delivery_worker.task is None or config_delivery_worker.task.done():
            raise RuntimeError("Configuration delivery worker unavailable")

    async def check(name, operation):
        try:
            await asyncio.wait_for(operation(), timeout=3)
            return name, "ok"
        except Exception:
            return name, "fail"

    checks = dict(await asyncio.gather(*(check(name, operation) for name, operation in
        [("postgres", database), ("redis", cache), ("rabbitmq", broker), ("storage", storage),
         ("notifications", notifications), ("config_delivery", config_delivery)])))
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(status_code=200 if ready else 503, content=ApiResponse.ok(
        {"status": "ready" if ready else "degraded", "checks": checks}).model_dump(mode="json"))


@router.get("/health/status")
async def status():
    return ApiResponse.ok({"service": "VisionGuard AI Backend", "version": "1.0.0", "environment": settings.ENVIRONMENT})
