import structlog
import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractRobustConnection

from src.core.settings import settings

log = structlog.get_logger()

_connection: AbstractRobustConnection | None = None


async def init_rabbitmq() -> None:
    global _connection
    _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)

    channel = await _connection.channel()
    await channel.set_qos(prefetch_count=10)

    # Declare exchanges
    ai_events_exchange = await channel.declare_exchange(
        "ai_worker_events", aio_pika.ExchangeType.TOPIC, durable=True
    )

    # Declare queues with Dead Letter Queue
    dlq = await channel.declare_queue("dlq.ai_events", durable=True)

    queue = await channel.declare_queue(
        "backend.ai_events",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": "dlq.ai_events",
        },
    )

    await queue.bind(ai_events_exchange, routing_key="events.*")

    await queue.consume(_dispatch_event)
    log.info("rabbitmq.consumer", status="listening", queue="backend.ai_events")


async def close_rabbitmq() -> None:
    if _connection:
        await _connection.close()


async def _dispatch_event(message: IncomingMessage) -> None:
    import json
    async with message.process(requeue=False):
        try:
            body = json.loads(message.body.decode())
            routing_key = message.routing_key
            log.info("rabbitmq.event_received", routing_key=routing_key, event_id=body.get("event_id"))

            await _route_event(routing_key, body)

        except Exception as e:
            log.error("rabbitmq.event_processing_failed", error=str(e))
            raise


async def _route_event(routing_key: str, body: dict) -> None:
    # Routes added as modules are built
    handlers = {
        "events.occupancy_updated":          _handle_occupancy_updated,
        "events.helmet_missing_detected":    _handle_ppe_violation,
        "events.vest_missing_detected":      _handle_ppe_violation,
        "events.gloves_missing_detected":    _handle_ppe_violation,
        "events.shoes_missing_detected":     _handle_ppe_violation,
        "events.overcrowding_detected":      _handle_overcrowding,
        "events.camera_offline_detected":    _handle_camera_offline,
        "events.camera_reconnected":         _handle_camera_reconnected,
        "events.worker_heartbeat":           _handle_worker_heartbeat,
    }
    handler = handlers.get(routing_key)
    if handler:
        await handler(body)
    else:
        log.warning("rabbitmq.unhandled_event", routing_key=routing_key)


async def _handle_ppe_violation(body: dict) -> None:
    log.info("event.ppe_violation", camera_id=body.get("camera_id"), type=body.get("event"))


async def _handle_occupancy_updated(body: dict) -> None:
    log.info("event.occupancy_updated", zone_id=body.get("zone_id"), count=body.get("count"))


async def _handle_overcrowding(body: dict) -> None:
    log.info("event.overcrowding", zone_id=body.get("zone_id"))


async def _handle_camera_offline(body: dict) -> None:
    log.warning("event.camera_offline", camera_id=body.get("camera_id"))


async def _handle_camera_reconnected(body: dict) -> None:
    log.info("event.camera_reconnected", camera_id=body.get("camera_id"))


async def _handle_worker_heartbeat(body: dict) -> None:
    log.debug("event.worker_heartbeat", worker_id=body.get("worker_id"))
