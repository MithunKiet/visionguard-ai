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
    channel = await _connection.channel(publisher_confirms=True)
    _exchange = await channel.declare_exchange(
        CONFIG_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    log.info("config_publisher.ready", exchange=CONFIG_EXCHANGE)


async def close_config_publisher() -> None:
    global _connection, _exchange
    if _connection:
        await _connection.close()
    _connection = None
    _exchange = None


async def publish_config_event(routing_key: str, payload: dict, *, require_confirm: bool = False) -> None:
    if _exchange is None:
        if require_confirm:
            raise RuntimeError("Config publisher unavailable")
        log.warning("config_publisher.not_initialized", routing_key=routing_key)
        return

    payload.setdefault("event_id", str(uuid.uuid4()))
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
        message_id=payload["event_id"],
    )
    # Workers use ephemeral fanout queues; no current subscriber is legitimate.
    # Confirmation proves broker acceptance only. HTTP reconciliation repairs
    # missed pushes and separate lease-bound reports prove application.
    confirmation = await _exchange.publish(message, routing_key=routing_key, mandatory=not require_confirm)
    if require_confirm and (confirmation is None or confirmation is False):
        raise RuntimeError("Config publication was not confirmed")
    log.info("config_publisher.sent", routing_key=routing_key, event_id=payload["event_id"])
