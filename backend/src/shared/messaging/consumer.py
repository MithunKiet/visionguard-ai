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
    ppe_keys = {
        "events.helmet_missing_detected",
        "events.vest_missing_detected",
        "events.gloves_missing_detected",
        "events.shoes_missing_detected",
        "events.mask_missing_detected",
    }
    if routing_key in ppe_keys:
        await _handle_ppe_violation(routing_key, body)
        return

    plain_handlers = {
        "events.occupancy_updated":       _handle_occupancy_updated,
        "events.overcrowding_detected":   _handle_overcrowding,
        "events.camera_offline_detected": _handle_camera_offline,
        "events.camera_reconnected":      _handle_camera_reconnected,
        "events.worker_heartbeat":        _handle_worker_heartbeat,
    }
    handler = plain_handlers.get(routing_key)
    if handler:
        await handler(body)
    else:
        log.warning("rabbitmq.unhandled_event", routing_key=routing_key)


async def _handle_ppe_violation(routing_key: str, body: dict) -> None:
    from uuid import UUID
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.ppe.application.services import PPEService
    from src.modules.ppe.infrastructure.repositories import ViolationRepository
    from src.modules.alerts.application.services import AlertService
    from src.modules.alerts.infrastructure.repositories import AlertRepository
    from src.modules.realtime.manager import manager

    async with AsyncSessionFactory() as db:
        ppe_svc = PPEService(ViolationRepository(db))
        violation = await ppe_svc.handle_violation_event(routing_key, body)

        await manager.broadcast(str(violation.enterprise_id), {
            "type": "violation.created",
            "data": await ppe_svc.enrich(violation),
        })

        # factory_id required for alert; AI worker must include it in the event payload
        factory_id = UUID(body["factory_id"]) if body.get("factory_id") else violation.zone_id
        alert_svc = AlertService(AlertRepository(db))
        alert = await alert_svc.create_from_violation(violation, factory_id)

        if alert:
            await manager.broadcast(str(violation.enterprise_id), {
                "type": "alert.created",
                "data": alert_svc.to_dict(alert),
            })


async def _handle_occupancy_updated(body: dict) -> None:
    log.info("event.occupancy_updated", zone_id=body.get("zone_id"), count=body.get("count"))


async def _handle_overcrowding(body: dict) -> None:
    log.info("event.overcrowding", zone_id=body.get("zone_id"))


async def _handle_camera_offline(body: dict) -> None:
    await _set_camera_status(body, "Offline")
    log.warning("event.camera_offline", camera_id=body.get("camera_id"))


async def _handle_camera_reconnected(body: dict) -> None:
    await _set_camera_status(body, "Active")
    log.info("event.camera_reconnected", camera_id=body.get("camera_id"))


async def _set_camera_status(body: dict, status: str) -> None:
    from uuid import UUID
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.camera.infrastructure.repositories import CameraRepository
    from src.modules.realtime.manager import manager

    camera_id = body.get("camera_id")
    enterprise_id = body.get("enterprise_id")
    if not camera_id:
        return

    async with AsyncSessionFactory() as db:
        await CameraRepository(db).set_status(UUID(camera_id), status)

    if enterprise_id:
        await manager.broadcast(enterprise_id, {
            "type": "camera.status_changed",
            "data": {"camera_id": camera_id, "status": status},
        })


async def _handle_worker_heartbeat(body: dict) -> None:
    # Registration + status is handled synchronously via POST /workers/heartbeat;
    # this event is published in parallel purely for log-based observability.
    log.debug("event.worker_heartbeat", worker_id=body.get("worker_id"))
