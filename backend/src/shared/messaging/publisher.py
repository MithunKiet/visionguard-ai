"""
Backend → AI Worker event publisher (config_events exchange).

Used to hot-push zone config changes, model updates, and camera assignment
changes to running AI workers without a restart (AI Worker rules #4, #12).
"""
import json
import uuid
from datetime import datetime, timezone

import aio_pika
import structlog
from aio_pika.abc import AbstractRobustConnection

from src.core.settings import settings

log = structlog.get_logger()

CONFIG_EXCHANGE = "config_events"

_connection: AbstractRobustConnection | None = None
_exchange = None


async def init_config_publisher() -> None:
    global _connection, _exchange
    _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await _connection.channel()
    _exchange = await channel.declare_exchange(
        CONFIG_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    log.info("config_publisher.ready", exchange=CONFIG_EXCHANGE)


async def close_config_publisher() -> None:
    if _connection:
        await _connection.close()


async def publish_config_event(routing_key: str, payload: dict) -> None:
    if _exchange is None:
        log.warning("config_publisher.not_initialized", routing_key=routing_key)
        return

    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    await _exchange.publish(message, routing_key=routing_key)
    log.info("config_publisher.sent", routing_key=routing_key, event_id=payload["event_id"])
