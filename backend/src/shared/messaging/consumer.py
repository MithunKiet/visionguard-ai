import structlog
import aio_pika
from aio_pika import IncomingMessage
from aio_pika.abc import AbstractRobustConnection

from src.core.settings import settings
from src.modules.worker.infrastructure.leases import fence_camera_event

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
    await channel.declare_queue("dlq.ai_events", durable=True)

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
    import asyncio
    import json
    from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError, TimeoutError as PoolTimeoutError
    async with message.process(requeue=False, ignore_processed=True):
        try:
            body = json.loads(message.body.decode())
            routing_key = message.routing_key
            log.info("rabbitmq.event_received", routing_key=routing_key, event_id=body.get("event_id"))

            await _route_event(routing_key, body)

        except asyncio.CancelledError:
            await message.nack(requeue=True)
            raise
        except Exception as e:
            sqlstate = getattr(getattr(e, "orig", None), "sqlstate", "") or ""
            transient = isinstance(e, (OSError, TimeoutError, PoolTimeoutError, InterfaceError, OperationalError)) or (
                isinstance(e, DBAPIError) and (e.connection_invalidated or sqlstate.startswith("08") or sqlstate in {"40001", "40P01", "57P01", "57P02", "57P03", "53300"}))
            log.error("rabbitmq.event_processing_failed", error_type=type(e).__name__, transient=transient)
            if transient:
                # Retain the original message/ID on the durable queue. Avoid
                # a tight redelivery loop while PostgreSQL is unavailable.
                try:
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    await message.nack(requeue=True)
                    raise
                await message.nack(requeue=True)
                return
            raise


async def _route_event(routing_key: str, body: dict) -> None:
    # Validate camera-bearing events before any handler can change tenant data.
    if body.get("camera_id"):
        from sqlalchemy import select
        from src.shared.database.models import Camera, Enterprise, Factory, Shift, Zone
        from src.shared.database.session import AsyncSessionFactory
        async with AsyncSessionFactory() as db:
            row = (await db.execute(select(Camera, Enterprise.public_id, Factory.public_id, Zone.public_id)
                .join(Enterprise, Enterprise.id == Camera.enterprise_id)
                .join(Factory, Factory.id == Camera.factory_id)
                .join(Zone, Zone.id == Camera.zone_id)
                .where(Camera.public_id == body["camera_id"], Camera.deleted_at.is_(None),
                       Factory.deleted_at.is_(None), Zone.deleted_at.is_(None)))).first()
            if row is None or body.get("enterprise_id") != row[1] or (body.get("factory_id") and body["factory_id"] != row[2]) or (body.get("zone_id") and body["zone_id"] != row[3]):
                raise ValueError("Event resource ownership mismatch")
            if body.get("shift_id"):
                shift = await db.scalar(select(Shift.id).where(Shift.public_id == body["shift_id"], Shift.factory_id == row[0].factory_id))
                if shift is None:
                    raise ValueError("Event shift ownership mismatch")
    # Routes added as modules are built
    ppe_keys = {
        "events.helmet_missing_detected",
        "events.vest_missing_detected",
        "events.gloves_missing_detected",
        "events.shoes_missing_detected",
        "events.mask_missing_detected",
        "events.low_confidence_violation",
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
        "events.camera_spec_mismatch":    _handle_camera_spec_mismatch,
    }
    handler = plain_handlers.get(routing_key)
    if handler:
        await handler(body)
    else:
        log.warning("rabbitmq.unhandled_event", routing_key=routing_key)


async def _handle_ppe_violation(routing_key: str, body: dict) -> None:
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.ppe.application.services import PPEService
    from src.modules.ppe.infrastructure.repositories import ViolationRepository
    from src.modules.alerts.application.services import AlertService
    from src.modules.alerts.infrastructure.repositories import AlertRepository
    from src.modules.realtime.manager import manager

    from uuid import UUID
    from datetime import datetime, timezone
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert
    from src.shared.database.models import Camera, Enterprise, EventReceipt, Zone
    from src.modules.maintenance.application.services import MaintenanceService
    from src.modules.shifts.application.services import ShiftService

    event_id = str(UUID(body["event_id"]))
    async with AsyncSessionFactory() as db:
        db.info["defer_commit"] = True
        async with db.begin():
            receipt = await db.execute(insert(EventReceipt).values(event_id=event_id)
                                       .on_conflict_do_nothing().returning(EventReceipt.event_id))
            if receipt.scalar_one_or_none() is None:
                return
            camera = (await db.execute(select(Camera).join(Enterprise, Enterprise.id == Camera.enterprise_id)
                .join(Zone, Zone.id == Camera.zone_id).where(
                    Camera.public_id == body["camera_id"], Enterprise.public_id == body["enterprise_id"],
                    Zone.public_id == body["zone_id"], Camera.deleted_at.is_(None), Zone.deleted_at.is_(None),
                ).with_for_update(of=Camera))).scalar_one_or_none()
            if camera is None:
                raise ValueError("Event camera/zone/enterprise mismatch")
            await fence_camera_event(db, body, historical=True)
            db.info["enterprise_id"] = body["enterprise_id"]
            from src.shared.database.models import Factory
            factory_id = await db.scalar(select(Factory.public_id).where(Factory.id == camera.factory_id))
            if body.get("factory_id") and body["factory_id"] != factory_id:
                raise ValueError("Event factory mismatch")
            occurred_at = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00")) if body.get("timestamp") else datetime.now(timezone.utc)
            shift = await ShiftService(db).find_active_for_factory(body["enterprise_id"], factory_id, occurred_at)
            body = {**body, "shift_id": shift.public_id if shift else None}
            ppe_svc = PPEService(ViolationRepository(db), db)
            violation = await ppe_svc.handle_violation_event(routing_key, body)
            alert_svc = AlertService(AlertRepository(db))
            if not violation.needs_review and not await MaintenanceService.is_in_maintenance(db, violation.camera_id):
                await alert_svc.create_from_violation(violation, factory_id)
        db.info["defer_commit"] = False
        # Alert delivery is already durable. Live violation refresh is best
        # effort; a Redis outage must not reject a committed receipt/alert.
        try:
            await manager.broadcast(str(violation.enterprise_id), {"type": "violation.created", "data": ppe_svc.enrich(violation)})
        except Exception as error:
            log.warning("violation.live_refresh_failed", error_type=type(error).__name__)


async def _handle_occupancy_updated(body: dict) -> None:
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.occupancy.application.services import OccupancyService
    from src.modules.occupancy.infrastructure.repositories import OccupancyRepository
    from src.modules.realtime.manager import manager

    if not (body.get("enterprise_id") and body.get("zone_id") and body.get("camera_id")):
        log.warning("event.occupancy_updated.missing_fields", body=body)
        return

    async with AsyncSessionFactory() as db:
        await fence_camera_event(db, body)
        svc = OccupancyService(OccupancyRepository(db))
        entry = await svc.handle_occupancy_event(body)

    await manager.broadcast(str(entry.enterprise_id), {
        "type": "occupancy.updated",
        "data": svc.to_dict(entry),
    })


async def _claim_alert_event(db, body):
    from uuid import UUID
    from sqlalchemy.dialects.postgresql import insert
    from src.shared.database.models import EventReceipt

    event_id = str(UUID(body["event_id"]))
    receipt = await db.execute(insert(EventReceipt).values(event_id=event_id)
        .on_conflict_do_nothing().returning(EventReceipt.event_id))
    return receipt.scalar_one_or_none() is not None


async def _handle_overcrowding(body: dict) -> None:
    await _handle_infrastructure_alert(body, "OVERCROWDING", "High", 120)


async def _handle_camera_spec_mismatch(body: dict) -> None:
    await _handle_infrastructure_alert(body, "CAMERA_SPEC_MISMATCH", "Low", 600)


async def _handle_infrastructure_alert(body, alert_type, severity, cooldown):
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.alerts.application.services import AlertService
    from src.modules.alerts.infrastructure.repositories import AlertRepository
    from src.modules.maintenance.application.services import MaintenanceService
    from src.modules.audit.application.services import AuditService

    required = ("event_id", "enterprise_id", "factory_id", "zone_id", "camera_id")
    if not all(body.get(key) for key in required):
        raise ValueError("Alert event is missing required fields")
    async with AsyncSessionFactory() as db:
        db.info["defer_commit"] = True
        async with db.begin():
            if not await _claim_alert_event(db, body):
                return
            await fence_camera_event(db, body, historical=True)
            db.info["enterprise_id"] = body["enterprise_id"]
            if alert_type == "OVERCROWDING" and await MaintenanceService.is_in_maintenance(db, body["camera_id"]):
                return
            await AlertService(AlertRepository(db)).create_event_alert(
                enterprise_id=body["enterprise_id"], factory_id=body["factory_id"],
                zone_id=body["zone_id"], camera_id=body["camera_id"],
                alert_type=alert_type, severity=severity, cooldown_seconds=cooldown,
            )
        db.info["defer_commit"] = False
        if alert_type == "CAMERA_SPEC_MISMATCH":
            await AuditService(db).record(
                enterprise_id=body["enterprise_id"], user_id=None, action=alert_type,
                entity_type="camera", entity_id=body["camera_id"],
                new_value={key: body.get(key) for key in
                    ("actual_fps", "actual_width", "actual_height", "expected_fps", "expected_width", "expected_height")},
            )


async def _handle_camera_offline(body: dict) -> None:
    await _set_camera_status(body, "Offline")
    log.warning("event.camera_offline", camera_id=body.get("camera_id"))


async def _handle_camera_reconnected(body: dict) -> None:
    await _set_camera_status(body, "Active")
    log.info("event.camera_reconnected", camera_id=body.get("camera_id"))


async def _set_camera_status(body: dict, status: str) -> None:
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.camera.infrastructure.repositories import CameraRepository
    from src.modules.realtime.manager import manager

    camera_id = body.get("camera_id")
    enterprise_id = body.get("enterprise_id")
    if not camera_id:
        return

    async with AsyncSessionFactory() as db:
        await fence_camera_event(db, body)
        changed = await CameraRepository(db).set_status(camera_id, status, preserve_inactive=True)

    if changed and enterprise_id:
        await manager.broadcast(enterprise_id, {
            "type": "camera.status_changed",
            "data": {"camera_id": camera_id, "status": status},
        })


async def _handle_worker_heartbeat(body: dict) -> None:
    # Registration + status is handled synchronously via POST /workers/heartbeat;
    # this event is published in parallel purely for log-based observability.
    log.debug("event.worker_heartbeat", worker_id=body.get("worker_id"))
