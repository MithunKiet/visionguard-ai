"""Durable incident acceptance and independent background network delivery."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone
import io
import json
import time
import uuid

import aio_pika
import cv2
from minio import Minio
import structlog
import urllib3

from src.config.settings import settings
from src.events.delivery import EdgeDelivery
from src.events.journal import EdgeJournal
from src.health.metrics import edge_rejected

log = structlog.get_logger()
DURABLE_ROUTES = {f"events.{name}" for name in (
    "helmet_missing_detected", "vest_missing_detected", "gloves_missing_detected", "shoes_missing_detected",
    "mask_missing_detected", "low_confidence_violation", "overcrowding_detected", "camera_spec_mismatch",
)}
_connection = None
_exchange = None
_journal = None
_delivery = None
_telemetry_task = None
_telemetry = OrderedDict()
_wire_lock = None
_storage = None


def get_journal():
    if _journal is None:
        raise RuntimeError("Edge journal not initialized")
    return _journal


async def init_publisher():
    global _journal, _delivery, _telemetry_task, _wire_lock, _storage
    if _journal is not None:
        raise RuntimeError("Publisher already initialized")
    _journal = await asyncio.to_thread(EdgeJournal, settings.EDGE_STATE_DIR,
        {"worker_id": settings.WORKER_ID, "enterprise_id": settings.ENTERPRISE_ID},
        max_events=settings.EDGE_MAX_EVENTS, max_bytes=settings.EDGE_MAX_BYTES,
        min_free_bytes=settings.EDGE_MIN_FREE_BYTES)
    try:
        _wire_lock = asyncio.Lock()
        _storage = Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY, secure=settings.MINIO_SECURE,
            http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=3, read=settings.EDGE_NETWORK_TIMEOUT_SECONDS),
                                            retries=False))
        _delivery = EdgeDelivery(_journal, _send_event, _send_evidence)
        _delivery.start()
        _telemetry_task = asyncio.create_task(_flush_telemetry())
        log.info("publisher.local_ready", worker_id=settings.WORKER_ID)
    except BaseException:
        await close_publisher()
        raise


async def close_publisher():
    global _journal, _connection, _exchange, _delivery, _telemetry_task
    if _telemetry_task:
        _telemetry_task.cancel()
        await asyncio.gather(_telemetry_task, return_exceptions=True)
        _telemetry_task = None
    if _delivery:
        await _delivery.stop()
        _delivery = None
    if _connection:
        try:
            await asyncio.wait_for(_connection.close(), timeout=5)
        except Exception:
            pass
    _connection = _exchange = None
    _telemetry.clear()
    if _journal:
        await asyncio.to_thread(_journal.close)
        _journal = None


def _payload(payload):
    body = dict(payload)
    body.setdefault("event_id", str(uuid.uuid4()))
    body.setdefault("worker_id", settings.WORKER_ID)
    body.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return body


async def _accept(route, body, snapshot=None):
    try:
        await asyncio.to_thread(get_journal().enqueue, route, body, snapshot)
    except Exception as error:
        edge_rejected.inc()
        log.error("edge.event_not_saved", event_id=body["event_id"], error_type=type(error).__name__)
        raise


async def publish(routing_key, payload):
    body = _payload(payload)
    if routing_key in DURABLE_ROUTES:
        await _accept(routing_key, body)
    else:
        # Current-state telemetry is bounded and best effort; it cannot fill the
        # durable incident budget or replay obsolete camera state after restart.
        key = (body.get("camera_id", "worker"), "camera_status" if routing_key in {
            "events.camera_offline_detected", "events.camera_reconnected"} else routing_key)
        _telemetry[key] = (time.monotonic(), routing_key, body)
        _telemetry.move_to_end(key)
        while len(_telemetry) > 2048:
            _telemetry.popitem(last=False)


async def publish_incident(routing_key, payload, frame):
    body = _payload(payload)
    try:
        def encode():
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError("Snapshot encoding failed")
            return encoded.tobytes()
        snapshot = await asyncio.to_thread(encode)
    except Exception as error:
        # Detection metadata remains useful even if image encoding fails.
        snapshot = None
        body["snapshot_unavailable_reason"] = "encoding_failed"
        log.warning("edge.snapshot_encoding_failed", error_type=type(error).__name__)
    if snapshot is not None:
        prefix = "/".join(str(body[name]) for name in ("enterprise_id", "factory_id", "zone_id", "camera_id"))
        body["snapshot_key"] = f"{prefix}/{body['event_id']}.jpg"
    else:
        body["snapshot_key"] = None
    await _accept(routing_key, body, snapshot)


async def _send_wire(route, body):
    global _connection, _exchange
    async with _wire_lock:
        try:
            async with asyncio.timeout(settings.EDGE_NETWORK_TIMEOUT_SECONDS):
                if _connection is None or _connection.is_closed:
                    _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL,
                        timeout=settings.EDGE_NETWORK_TIMEOUT_SECONDS, fail_fast=True)
                    channel = await _connection.channel(publisher_confirms=True, on_return_raises=True)
                    _exchange = await channel.declare_exchange("ai_worker_events", aio_pika.ExchangeType.TOPIC, durable=True)
                message = aio_pika.Message(body=json.dumps(body).encode(), message_id=body["event_id"],
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT, content_type="application/json")
                await _exchange.publish(message, routing_key=route, mandatory=True,
                                        timeout=settings.EDGE_NETWORK_TIMEOUT_SECONDS)
        except BaseException:
            connection, _connection, _exchange = _connection, None, None
            if connection:
                try:
                    await asyncio.wait_for(connection.close(), timeout=3)
                except Exception:
                    pass
            raise


async def _send_event(row, body):
    await _send_wire(row["routing_key"], body)


async def _send_evidence(row, body):
    # Socket timeouts bound native I/O. Do not start overlapping retry threads
    # via wait_for: cancellation cannot interrupt a running MinIO upload.
    await asyncio.to_thread(_storage.put_object, settings.MINIO_BUCKET_SNAPSHOTS,
        body["snapshot_key"], io.BytesIO(row["snapshot"]), len(row["snapshot"]), content_type="image/jpeg")


async def _flush_telemetry():
    while True:
        if _telemetry:
            _, (created, route, body) = _telemetry.popitem(last=False)
            if time.monotonic() - created < 60:
                try:
                    await _send_wire(route, body)
                except Exception:
                    log.debug("edge.telemetry_delivery_failed")
        await asyncio.sleep(0.1)
