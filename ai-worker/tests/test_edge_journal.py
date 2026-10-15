import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import numpy as np
import pytest

from src.config import assignment_cache
from src.config.settings import settings
from src.events import journal as journal_module, publisher
from src.events.delivery import EdgeDelivery
from src.events.journal import EdgeJournal, JournalFull

IDENTITY = {"worker_id": "test-worker", "enterprise_id": str(uuid4())}
ROUTE = "events.helmet_missing_detected"


def payload():
    return {"event_id": str(uuid4()), "event": "helmet_missing_detected", "enterprise_id": IDENTITY["enterprise_id"],
            "camera_id": str(uuid4()), "factory_id": str(uuid4()), "zone_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(), "snapshot_key": "test/snapshot.jpg"}


@pytest.fixture
def journal(tmp_path):
    store = EdgeJournal(tmp_path / "state", IDENTITY, min_free_bytes=0)
    yield store
    store.close()


def test_atomic_event_and_snapshot_survive_restart(journal):
    body = payload()
    journal.enqueue(ROUTE, body, b"jpeg")
    journal.close()
    reopened = EdgeJournal(journal.directory, IDENTITY, min_free_bytes=0)
    try:
        event = reopened.next_due("event")
        assert json.loads(event["payload"]) == body
        assert reopened.next_due("evidence")["snapshot"] == b"jpeg"
        reopened.succeeded(body["event_id"], "event")
        assert reopened.stats()["rows"] == 1
        reopened.succeeded(body["event_id"], "evidence")
        assert reopened.stats()["rows"] == 0
    finally:
        reopened.close()


def test_committed_record_survives_abrupt_process_exit(tmp_path):
    directory = str(tmp_path / "crash")
    body = payload()
    script = """import json,os,sys
from src.events.journal import EdgeJournal
j=EdgeJournal(sys.argv[1], json.loads(sys.argv[2]), min_free_bytes=0)
j.enqueue('events.helmet_missing_detected',json.loads(sys.argv[3]),b'jpeg')
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", script, directory, json.dumps(IDENTITY), json.dumps(body)], check=True)
    store = EdgeJournal(directory, IDENTITY, min_free_bytes=0)
    try:
        assert store.next_due("event")["event_id"] == body["event_id"]
        assert store.next_due("evidence")["snapshot"] == b"jpeg"
    finally:
        store.close()


def test_exclusive_owner_identity_binding_and_permissions(journal):
    with pytest.raises(RuntimeError, match="active owner"):
        EdgeJournal(journal.directory, IDENTITY)
    assert journal.directory.stat().st_mode & 0o777 == 0o700
    assert journal.path.stat().st_mode & 0o777 == 0o600
    journal.close()
    with pytest.raises(RuntimeError, match="different worker"):
        EdgeJournal(journal.directory, {**IDENTITY, "enterprise_id": str(uuid4())})


def test_full_journal_preserves_old_incident_and_rejects_new_one(tmp_path):
    store = EdgeJournal(tmp_path / "limited", IDENTITY, max_events=1, min_free_bytes=0)
    old = payload()
    try:
        store.enqueue(ROUTE, old, b"original")
        with pytest.raises(JournalFull):
            store.enqueue(ROUTE, payload(), b"new")
        assert store.next_due("event")["event_id"] == old["event_id"]
        store.enqueue(ROUTE, old, b"original")  # Same accepted event may be retried.
        with pytest.raises(ValueError, match="Conflicting"):
            store.enqueue(ROUTE, {**old, "confidence": 0.7})
    finally:
        store.close()


def test_byte_and_disk_reserve_limits_are_explicit(journal, monkeypatch):
    journal.max_bytes = 100000
    with pytest.raises(JournalFull):
        journal.enqueue(ROUTE, payload(), b"x" * 100001)
    monkeypatch.setattr(journal_module.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(JournalFull):
        journal.enqueue(ROUTE, payload(), b"image")
    assert journal.stats()["rows"] == 0


@pytest.mark.asyncio
async def test_broker_and_storage_retry_independently_with_original_identity(journal, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(journal_module, "time", SimpleNamespace(time=lambda: clock[0]))
    body = payload()
    journal.enqueue(ROUTE, body, b"jpeg")
    broker, storage = AsyncMock(side_effect=OSError("broker unavailable")), AsyncMock(side_effect=OSError("store unavailable"))
    delivery = EdgeDelivery(journal, broker, storage)
    await delivery.once("event")
    await delivery.once("evidence")
    assert journal.stats()["events"] == journal.stats()["evidence"] == 1
    assert not await delivery.once("event")  # Backoff, no busy retry.
    clock[0] += 2
    broker.side_effect = None
    await delivery.once("event")
    assert broker.await_args.args[1] == body
    assert journal.stats()["events"] == 0 and journal.stats()["evidence"] == 1
    await delivery.once("evidence")
    assert journal.stats()["rows"] == 1
    clock[0] += 4
    storage.side_effect = None
    await delivery.once("evidence")
    assert storage.await_args.args[0]["snapshot"] == b"jpeg"
    assert journal.stats()["rows"] == 0


@pytest.mark.asyncio
async def test_evidence_can_finish_while_broker_is_down(journal):
    journal.enqueue(ROUTE, payload(), b"jpeg")
    delivery = EdgeDelivery(journal, AsyncMock(side_effect=OSError()), AsyncMock())
    await delivery.once("evidence")
    assert journal.stats()["evidence"] == 0 and journal.stats()["events"] == 1
    await delivery.once("event")
    assert journal.stats()["events"] == 1


@pytest.mark.asyncio
async def test_ack_loss_replays_same_id_and_timestamp(journal, monkeypatch):
    body = payload()
    journal.enqueue(ROUTE, body)
    sender = AsyncMock()
    delivery = EdgeDelivery(journal, sender, AsyncMock())
    succeeded = journal.succeeded
    monkeypatch.setattr(journal, "succeeded", Mock(side_effect=OSError("crash after broker confirmation")))
    await delivery.once("event")
    monkeypatch.setattr(journal, "succeeded", succeeded)
    monkeypatch.setattr(journal, "failed", Mock())
    with journal._db() as db:
        db.execute("UPDATE events SET event_due=0")
    await delivery.once("event")
    assert [call.args[1] for call in sender.await_args_list] == [body, body]
    assert journal.stats()["rows"] == 0


@pytest.mark.asyncio
async def test_camera_accepts_snapshot_locally_without_any_network(journal, monkeypatch):
    from src.pipeline.camera_worker import CameraWorker
    from src.pipeline.types import Detection
    monkeypatch.setattr(publisher, "_journal", journal)
    worker = CameraWorker(str(uuid4()), "rtsp://example.invalid/feed", {"required_consecutive_frames": 1},
        IDENTITY["enterprise_id"], str(uuid4()), str(uuid4()),
        SimpleNamespace(detect=AsyncMock(return_value=[Detection("person", .99, (0, 0, 100, 200), False),
                                                     Detection("no_helmet", .99, (0, 0, 100, 200), True)])))
    worker._check_camera_spec = AsyncMock()
    worker._publish_occupancy = AsyncMock()
    worker._validator.acknowledge = Mock(wraps=worker._validator.acknowledge)
    await worker._process_frame(np.zeros((32, 32, 3), dtype=np.uint8))
    row = journal.next_due("event")
    assert row is not None and row["snapshot"].startswith(b"\xff\xd8")
    assert json.loads(row["payload"])["snapshot_key"].endswith(row["event_id"] + ".jpg")
    worker._validator.acknowledge.assert_called_once()
    await worker._process_frame(np.zeros((32, 32, 3), dtype=np.uint8))
    assert journal.stats()["rows"] == 1  # Cooldown starts at durable acceptance.


@pytest.mark.asyncio
async def test_encoding_failure_keeps_incident_and_disk_failure_is_not_acknowledged(journal, monkeypatch):
    monkeypatch.setattr(publisher, "_journal", journal)
    monkeypatch.setattr(publisher.cv2, "imencode", Mock(return_value=(False, None)))
    body = payload()
    await publisher.publish_incident(ROUTE, body, np.zeros((4, 4, 3), dtype=np.uint8))
    event = journal.next_due("event")
    assert json.loads(event["payload"])["snapshot_key"] is None
    assert event["snapshot"] is None
    monkeypatch.setattr(journal, "enqueue", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError):
        await publisher.publish(ROUTE, payload())


@pytest.mark.asyncio
async def test_telemetry_is_bounded_and_does_not_consume_durable_budget(journal, monkeypatch):
    monkeypatch.setattr(publisher, "_journal", journal)
    monkeypatch.setattr(publisher, "_telemetry", publisher.OrderedDict())
    for i in range(2100):
        await publisher.publish("events.occupancy_updated", {"camera_id": str(i), "count": 1})
    assert len(publisher._telemetry) == 2048 and journal.stats()["rows"] == 0
    await publisher.publish("events.camera_offline_detected", {"camera_id": "camera"})
    await publisher.publish("events.camera_reconnected", {"camera_id": "camera"})
    assert publisher._telemetry[("camera", "camera_status")][1] == "events.camera_reconnected"


def cameras():
    return [{**{key: str(uuid4()) for key in ("camera_id", "factory_id", "zone_id")},
             "enterprise_id": IDENTITY["enterprise_id"], "rtsp_url": "rtsp://example.invalid/private", "zone_config": {}}]


@pytest.mark.asyncio
async def test_cached_restart_requires_fresh_matching_authorization(journal, monkeypatch):
    monkeypatch.setattr(settings, "ENTERPRISE_ID", IDENTITY["enterprise_id"])
    body = cameras()
    assert await assignment_cache.refresh_assignments(journal, AsyncMock(), AsyncMock(return_value=body)) == body
    offline = AsyncMock(side_effect=httpx.ConnectError("offline"))
    assert await assignment_cache.refresh_assignments(journal, offline, AsyncMock()) == body
    monkeypatch.setattr(settings, "WORKER_API_KEY", "rotated-key")
    assert await assignment_cache.refresh_assignments(journal, offline, AsyncMock()) == []


@pytest.mark.parametrize("status", [400, 401, 403, 404])
@pytest.mark.asyncio
async def test_authorization_rejection_erases_cached_streams(journal, monkeypatch, status):
    monkeypatch.setattr(settings, "ENTERPRISE_ID", IDENTITY["enterprise_id"])
    journal.save_cache(cameras(), assignment_cache.authorization_identity())
    request = httpx.Request("GET", "https://backend.invalid")
    error = httpx.HTTPStatusError("denied", request=request, response=httpx.Response(status, request=request))
    assert await assignment_cache.refresh_assignments(journal, AsyncMock(side_effect=error), AsyncMock()) == []
    assert journal.load_cache(300, assignment_cache.authorization_identity()) == []


@pytest.mark.asyncio
async def test_cache_expiry_clock_rollback_and_authoritative_empty_list(journal, monkeypatch):
    monkeypatch.setattr(settings, "ENTERPRISE_ID", IDENTITY["enterprise_id"])
    clock = [100.0]
    monkeypatch.setattr(journal_module, "time", SimpleNamespace(time=lambda: clock[0]))
    body = cameras()
    await assignment_cache.refresh_assignments(journal, AsyncMock(), AsyncMock(return_value=body))
    offline = AsyncMock(side_effect=httpx.ConnectError("offline"))
    clock[0] = 500
    assert await assignment_cache.refresh_assignments(journal, offline, AsyncMock()) == []
    clock[0] = 50
    assert await assignment_cache.refresh_assignments(journal, offline, AsyncMock()) == []
    clock[0] = 101
    assert await assignment_cache.refresh_assignments(journal, AsyncMock(), AsyncMock(return_value=[])) == []
    assert await assignment_cache.refresh_assignments(journal, offline, AsyncMock()) == []


@pytest.mark.asyncio
async def test_cache_invalidation_during_http_fetch_cannot_restore_stale_config(journal, monkeypatch):
    monkeypatch.setattr(settings, "ENTERPRISE_ID", IDENTITY["enterprise_id"])
    async def fetch():
        journal.clear_cache()  # A config push was received while HTTP was in flight.
        return cameras()
    assert await assignment_cache.refresh_assignments(journal, AsyncMock(), fetch) == []
    assert journal.load_cache(300, assignment_cache.authorization_identity()) == []


@pytest.mark.asyncio
async def test_foreign_or_malformed_assignments_clear_cache(journal, monkeypatch):
    monkeypatch.setattr(settings, "ENTERPRISE_ID", IDENTITY["enterprise_id"])
    journal.save_cache(cameras(), assignment_cache.authorization_identity())
    foreign = cameras()
    foreign[0]["enterprise_id"] = str(uuid4())
    assert await assignment_cache.refresh_assignments(journal, AsyncMock(), AsyncMock(return_value=foreign)) == []
    assert journal.load_cache(300, assignment_cache.authorization_identity()) == []


@pytest.mark.asyncio
async def test_publisher_starts_offline_and_closes_local_state(journal, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "EDGE_STATE_DIR", str(tmp_path / "startup"))
    monkeypatch.setattr(settings, "EDGE_MIN_FREE_BYTES", 0)
    monkeypatch.setattr(publisher, "_journal", None)
    connect = AsyncMock(side_effect=OSError("offline"))
    monkeypatch.setattr(publisher.aio_pika, "connect_robust", connect)
    try:
        await publisher.init_publisher()
        connect.assert_not_called()  # Startup does not await any broker handshake.
        await publisher.publish(ROUTE, payload())
        assert publisher.get_journal().stats()["rows"] == 1
    finally:
        await publisher.close_publisher()
    assert Path(settings.EDGE_STATE_DIR, "events.sqlite3").exists()


@pytest.mark.asyncio
async def test_camera_does_not_start_cooldown_when_durable_acceptance_fails(monkeypatch):
    from src.pipeline import camera_worker
    worker = camera_worker.CameraWorker.__new__(camera_worker.CameraWorker)
    worker._active = True
    worker.camera_id, worker.factory_id, worker.zone_id = str(uuid4()), str(uuid4()), str(uuid4())
    worker.enterprise_id = IDENTITY["enterprise_id"]
    worker.zone_config = {}
    worker._check_camera_spec = AsyncMock()
    worker._detector = SimpleNamespace(detect=AsyncMock(return_value=[]))
    worker._validator = Mock()
    worker._validator.evaluate.return_value = [{"event": "helmet_missing_detected", "confidence": .9,
                                                "bbox": [0, 0, 1, 1]}]
    monkeypatch.setattr(camera_worker, "publish_incident", AsyncMock(side_effect=JournalFull("full")))
    with pytest.raises(JournalFull):
        await worker._process_frame(np.zeros((4, 4, 3), dtype=np.uint8))
    worker._validator.acknowledge.assert_not_called()


@pytest.mark.asyncio
async def test_runtime_can_boot_from_cache_and_always_closes_local_state(journal, monkeypatch):
    from src import main as runtime
    monkeypatch.setattr(settings, "ENTERPRISE_ID", IDENTITY["enterprise_id"])
    assignments = cameras()
    journal.save_cache(assignments, assignment_cache.authorization_identity())
    detector = SimpleNamespace(start=Mock(), stop=AsyncMock())
    sync = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(runtime, "start_metrics_server", Mock())
    monkeypatch.setattr(runtime, "init_publisher", AsyncMock())
    close = AsyncMock()
    monkeypatch.setattr(runtime, "close_publisher", close)
    monkeypatch.setattr(runtime, "get_journal", lambda: journal)
    monkeypatch.setattr(runtime, "BatchDetector", lambda: detector)
    monkeypatch.setattr(runtime, "ZoneConfigSync", lambda *a, **kw: sync)
    monkeypatch.setattr(runtime, "register_worker", AsyncMock(side_effect=httpx.ConnectError("offline")))
    fetch = AsyncMock()
    monkeypatch.setattr(runtime, "fetch_assigned_cameras", fetch)
    reconcile = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(runtime, "reconcile_cameras", reconcile)
    with pytest.raises(asyncio.CancelledError):
        await runtime.main()
    assert reconcile.await_args.args[3] == assignments
    fetch.assert_not_called()
    close.assert_awaited_once()
    detector.stop.assert_awaited_once()
    sync.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_subscriber_start_does_not_wait_for_broker(monkeypatch):
    from src.config.zone_sync import ZoneConfigSync
    connect = AsyncMock(side_effect=OSError("offline"))
    monkeypatch.setattr(publisher.aio_pika, "connect_robust", connect)
    sync = ZoneConfigSync([])
    await sync.start()
    await asyncio.sleep(0)
    assert sync._task and not sync._task.done()
    await sync.stop()
    assert sync._task is None


@pytest.mark.skipif(not os.environ.get("TEST_RABBITMQ_URL"), reason="Requires dedicated test RabbitMQ")
@pytest.mark.asyncio
async def test_real_broker_confirmed_replay_preserves_message_identity(journal, monkeypatch):
    import aio_pika
    monkeypatch.setattr(settings, "RABBITMQ_URL", os.environ["TEST_RABBITMQ_URL"])
    monkeypatch.setattr(publisher, "_wire_lock", asyncio.Lock())
    route = "edge_test." + uuid4().hex  # Does not match the application's events.* consumer.
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange("ai_worker_events", aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        await queue.bind(exchange, routing_key=route)
        body = payload()
        journal.enqueue(route, body)
        row = journal.next_due("event")
        await publisher._send_event(row, body)
        await publisher._send_event(row, body)  # Simulate restart before local completion commit.
        for _ in range(2):
            message = await queue.get(timeout=5)
            assert message.message_id == body["event_id"] and json.loads(message.body) == body
            await message.ack()
        await queue.unbind(exchange, routing_key=route)
        with pytest.raises(Exception):
            await publisher._send_event(row, body)  # Unroutable mandatory delivery must fail.
        assert journal.stats()["events"] == 1
    finally:
        await connection.close()
        await publisher.close_publisher()
