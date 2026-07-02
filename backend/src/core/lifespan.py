import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.shared.database.session import init_db
from src.shared.cache.client import init_redis, close_redis
from src.shared.messaging.consumer import init_rabbitmq, close_rabbitmq
from src.shared.messaging.publisher import init_config_publisher, close_config_publisher
from src.shared.storage.minio_client import init_minio

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("visionguard.startup", msg="Starting VisionGuard AI backend...")

    await init_db()
    log.info("visionguard.startup", service="postgres", status="connected")

    await init_redis()
    log.info("visionguard.startup", service="redis", status="connected")

    await init_rabbitmq()
    await init_config_publisher()
    log.info("visionguard.startup", service="rabbitmq", status="connected")

    await init_minio()
    log.info("visionguard.startup", service="minio", status="ready")

    log.info("visionguard.startup", msg="All services ready. VisionGuard AI is running.")

    yield

    log.info("visionguard.shutdown", msg="Shutting down...")
    await close_redis()
    await close_config_publisher()
    await close_rabbitmq()
    log.info("visionguard.shutdown", msg="Shutdown complete.")
