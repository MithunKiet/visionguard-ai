import json
import uuid
import structlog
import aio_pika
from datetime import datetime, timezone

from src.config.settings import settings

log = structlog.get_logger()

_connection = None
_channel = None
_exchange = None


async def init_publisher() -> None:
    global _connection, _channel, _exchange
    _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        "ai_worker_events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    log.info("publisher.ready", worker_id=settings.WORKER_ID)


async def close_publisher() -> None:
    if _connection:
        await _connection.close()


async def publish(routing_key: str, payload: dict) -> None:
    if _exchange is None:
        raise RuntimeError("Publisher not initialized")

    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("worker_id", settings.WORKER_ID)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    await _exchange.publish(message, routing_key=routing_key)
    log.debug("publisher.sent", routing_key=routing_key, event_id=payload["event_id"])
