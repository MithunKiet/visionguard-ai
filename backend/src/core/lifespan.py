import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.shared.database.session import init_db
from src.modules.realtime.manager import manager
from src.shared.cache.client import init_redis, close_redis
from src.shared.messaging.consumer import init_rabbitmq, close_rabbitmq
from src.shared.messaging.publisher import init_config_publisher, close_config_publisher
from src.shared.storage.minio_client import init_minio
from src.modules.notifications.application.outbox import delivery_worker
from src.modules.config.application.delivery import config_delivery_worker

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("visionguard.startup", msg="Starting VisionGuard AI backend...")

    await init_db()
    log.info("visionguard.startup", service="postgres", status="connected")

    await init_redis()
    log.info("visionguard.startup", service="redis", status="connected")

    await manager.start()
    await init_rabbitmq()
    await init_config_publisher()
    log.info("visionguard.startup", service="rabbitmq", status="connected")

    await init_minio()
    log.info("visionguard.startup", service="minio", status="ready")
    delivery_worker.start()
    config_delivery_worker.start()

    log.info("visionguard.startup", msg="All services ready. VisionGuard AI is running.")

    try:
        yield
    finally:
        log.info("visionguard.shutdown", msg="Shutting down...")
        await close_rabbitmq()
        await delivery_worker.stop()
        await config_delivery_worker.stop()
        await manager.stop()
        await close_config_publisher()
        await close_redis()
        log.info("visionguard.shutdown", msg="Shutdown complete.")
