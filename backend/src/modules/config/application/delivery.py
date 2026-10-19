"""Restart-safe configuration publication with bounded attempts and backoff."""
import asyncio
from datetime import timedelta
import random

from sqlalchemy import func, select
import structlog

from src.shared.database.models import ConfigDelivery
from src.shared.database.session import AsyncSessionFactory
from src.shared.messaging.publisher import publish_config_event

log = structlog.get_logger()


class ConfigDeliveryWorker:
    def __init__(self):
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def run(self):
        while True:
            try:
                if await self.process_one():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.error("config_delivery.failed", error_type=type(error).__name__)
            await asyncio.sleep(2)

    async def process_one(self, event_id=None):
        async with AsyncSessionFactory() as db, db.begin():
            query = select(ConfigDelivery).where(
                ConfigDelivery.status.in_(["Pending", "Retrying"]),
                ConfigDelivery.next_attempt_at <= func.now(),
            ).order_by(ConfigDelivery.next_attempt_at, ConfigDelivery.event_id).limit(1).with_for_update(skip_locked=True)
            if event_id:
                query = query.where(ConfigDelivery.event_id == event_id)
            job = await db.scalar(query)
            if job is None:
                return False
            job.attempts += 1
            try:
                # A crash after confirmation may redeliver. Stable IDs and
                # monotonically applied versions make that safe.
                await asyncio.wait_for(publish_config_event(
                    "config.zone_config_updated", dict(job.payload), require_confirm=True), timeout=5)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                job.status = "Retrying"
                job.last_error = type(error).__name__[:100]
                now = await db.scalar(select(func.clock_timestamp()))
                delay = min(300, 2 ** min(job.attempts, 9)) * random.uniform(0.8, 1.0)
                job.next_attempt_at = now + timedelta(seconds=delay)
            else:
                job.status = "Published"
                job.last_error = None
                job.published_at = await db.scalar(select(func.clock_timestamp()))
        log.info("config_delivery.attempt", event_id=job.event_id, status=job.status, attempt=job.attempts)
        return True


config_delivery_worker = ConfigDeliveryWorker()
