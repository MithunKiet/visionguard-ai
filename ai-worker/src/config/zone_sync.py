"""
Zone config hot-reload (AI Worker rules #4, #8, #12).

Subscribes to the backend's `config_events` exchange and applies
zone_config_updated events to running CameraWorkers in-place — no stream
restart. Rule #4: an event is applied only if event.version > local version;
stale/duplicate events are discarded.
"""
import json

import aio_pika
import structlog

from src.config.settings import settings

log = structlog.get_logger()

CONFIG_EXCHANGE = "config_events"

_connection = None


class ZoneConfigSync:

    def __init__(self, camera_workers: list):
        # CameraWorker instances, matched by zone_id on each event
        self._workers = camera_workers

    async def start(self) -> None:
        global _connection
        _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        channel = await _connection.channel()
        exchange = await channel.declare_exchange(
            CONFIG_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        # Exclusive auto-delete queue per worker process — every worker gets
        # every config event and applies only those for its own zones.
        queue = await channel.declare_queue(
            f"worker.{settings.WORKER_ID}.config", exclusive=True, auto_delete=True
        )
        await queue.bind(exchange, routing_key="config.*")
        await queue.consume(self._on_message)
        log.info("zone_sync.listening", worker_id=settings.WORKER_ID)

    async def stop(self) -> None:
        if _connection:
            await _connection.close()

    async def _on_message(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                body = json.loads(message.body.decode())
            except json.JSONDecodeError:
                log.warning("zone_sync.bad_payload")
                return

            if message.routing_key == "config.zone_config_updated":
                self._apply_zone_config(body)
            else:
                log.debug("zone_sync.ignored_event", routing_key=message.routing_key)

    def _apply_zone_config(self, body: dict) -> None:
        zone_id = body.get("zone_id")
        new_config = body.get("config") or {}
        new_version = int(new_config.get("version", 0))

        for worker in self._workers:
            if worker.zone_id != zone_id:
                continue
            local_version = int(worker.zone_config.get("version", 1))
            if new_version <= local_version:
                log.info("zone_sync.stale_config_discarded", zone_id=zone_id,
                         local=local_version, received=new_version)
                continue
            worker.apply_zone_config(new_config)
            log.info("zone_sync.config_applied", zone_id=zone_id,
                     camera_id=worker.camera_id, version=new_version)
