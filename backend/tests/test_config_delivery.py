"""PostgreSQL atomic delivery, retry recovery and current-owner confirmations."""
import asyncio
from datetime import timedelta
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update

from src.core.settings import settings
from src.modules.config.application.delivery import ConfigDeliveryWorker
from src.modules.config.application.services import ConfigService
from src.modules.worker.infrastructure.leases import CameraLeaseRepository
from src.shared.database.models import AIWorker, Camera, CameraConfigApplication, CameraLease, ConfigDelivery, ConfigHistory, ZoneConfig
from src.shared.database.session import AsyncSessionFactory, engine
from src.shared.messaging import publisher
from tests.test_review_integration import headers, setup as setup

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL and Redis")


async def save(s):
    async with AsyncSessionFactory() as db:
        return await ConfigService(db).update_zone_config(s.places[0].zone.public_id, s.enterprise.public_id,
            {"required_ppe_types": ["helmet"]}, s.users["admin"].public_id)


async def job_for(s):
    async with AsyncSessionFactory() as db:
        return await db.scalar(select(ConfigDelivery).where(ConfigDelivery.zone_id == s.places[0].zone.id)
            .order_by(ConfigDelivery.version.desc()))


async def status(s, caller="admin", zone=None):
    return await s.client.get(f"/api/v1/config/zone/{zone or s.places[0].zone.public_id}/delivery", headers=headers(s, caller))


async def make_ack(s, monkeypatch):
    session = str(uuid4())
    async with AsyncSessionFactory() as db:
        grants = await CameraLeaseRepository(db).acquire(s.enterprise.public_id, s.worker.id, session)
    camera_id = s.places[0].camera.public_id
    monkeypatch.setattr(settings, "WORKER_CREDENTIALS", {
        s.worker.worker_id: {"key": "test-config-worker", "enterprise_id": s.enterprise.public_id}})
    auth = {"X-Worker-Key": "test-config-worker", "X-Enterprise-Id": s.enterprise.public_id, "X-Worker-Session": session}
    item = {"camera_id": camera_id, "zone_id": s.places[0].zone.public_id,
            "lease_token": grants[camera_id]["token"], "version": 2}
    return auth, item


async def ack(s, auth, item, worker_id=None):
    return await s.client.post(f"/api/v1/workers/{worker_id or s.worker.worker_id}/config-applied",
                              headers=auth, json={"applications": [item]})


async def test_save_survives_broker_outage_and_new_dispatcher_retries(setup, monkeypatch):
    s = setup
    monkeypatch.setattr(publisher, "_exchange", None)
    response = await s.client.put(f"/api/v1/config/zone/{s.places[0].zone.public_id}", headers=headers(s),
                                  json={"helmet_threshold": 0.82})
    assert response.status_code == 200 and response.json()["data"]["version"] == 2
    job = await job_for(s)
    assert job.status == "Pending" and job.payload["config"]["helmet_threshold"] == .82
    assert await ConfigDeliveryWorker().process_one(job.event_id)
    failed = await job_for(s)
    assert failed.status == "Retrying" and failed.attempts == 1 and failed.last_error == "RuntimeError"
    assert not await ConfigDeliveryWorker().process_one(job.event_id)  # Backoff is honored.
    async with AsyncSessionFactory() as db:
        await db.execute(update(ConfigDelivery).where(ConfigDelivery.event_id == job.event_id).values(next_attempt_at=func.now()))
        await db.commit()
    exchange = AsyncMock()
    exchange.publish.return_value = True
    monkeypatch.setattr(publisher, "_exchange", exchange)
    assert await ConfigDeliveryWorker().process_one(job.event_id)
    published = await job_for(s)
    assert published.status == "Published" and published.attempts == 2 and published.last_error is None
    message = exchange.publish.await_args.args[0]
    assert message.message_id == job.event_id
    report = (await status(s)).json()["data"]
    assert report["status"] == "Pending" and report["publication"]["status"] == "Published"
    assert not await ConfigDeliveryWorker().process_one(job.event_id)


async def test_outbox_insert_failure_rolls_back_config_and_history(setup):
    s = setup
    def fail(*args):
        raise RuntimeError("injected outbox write failure")
    event.listen(ConfigDelivery, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            await save(s)
    finally:
        event.remove(ConfigDelivery, "before_insert", fail)
    async with AsyncSessionFactory() as db:
        config = await db.get(ZoneConfig, s.places[0].config.id)
        assert config.version == 1
        assert await db.scalar(select(func.count()).select_from(ConfigHistory).where(
            ConfigHistory.zone_id == s.places[0].zone.id)) == 0
    assert await job_for(s) is None


async def test_dispatchers_skip_locked_and_crash_rolls_back_attempt(setup, monkeypatch):
    await save(setup)
    job = await job_for(setup)
    entered, release = asyncio.Event(), asyncio.Event()
    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
    monkeypatch.setattr("src.modules.config.application.delivery.publish_config_event", slow)
    first = asyncio.create_task(ConfigDeliveryWorker().process_one(job.event_id))
    await asyncio.wait_for(entered.wait(), 3)
    try:
        assert not await asyncio.wait_for(ConfigDeliveryWorker().process_one(job.event_id), 2)
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
    current = await job_for(setup)
    assert current.status == "Pending" and current.attempts == 0
    publish = AsyncMock()
    monkeypatch.setattr("src.modules.config.application.delivery.publish_config_event", publish)
    assert await ConfigDeliveryWorker().process_one(job.event_id)
    assert publish.await_args.args[1]["event_id"] == job.event_id


async def test_applied_requires_current_version_and_live_process_lease(setup, monkeypatch):
    s = setup
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    assert (await status(s)).json()["data"]["status"] == "Pending"
    assert (await ack(s, auth, item)).json()["data"] == {"accepted": 1, "rejected": 0}
    first = (await status(s)).json()["data"]
    assert first["status"] == "Applied" and first["applied_cameras"] == 1
    assert first["publication"]["status"] == "Pending"  # HTTP reconciliation alone can apply.
    await ack(s, auth, item)
    assert (await status(s)).json()["data"]["last_applied_at"] == first["last_applied_at"]
    await save(s)
    assert (await status(s)).json()["data"]["status"] == "Pending"
    assert (await ack(s, auth, item)).json()["data"]["rejected"] == 1
    item["version"] = 3
    assert (await ack(s, auth, item)).json()["data"]["accepted"] == 1
    async with AsyncSessionFactory() as db:
        await db.execute(update(CameraLease).where(CameraLease.token == item["lease_token"])
                         .values(expires_at=func.now() - timedelta(seconds=1)))
        await db.commit()
    assert (await status(s)).json()["data"]["status"] == "Pending"
    assert (await ack(s, auth, item)).json()["data"]["rejected"] == 1
    new_auth, new_item = await make_ack(s, monkeypatch)
    new_item["version"] = 3
    assert new_item["lease_token"] != item["lease_token"]
    assert (await ack(s, auth, item)).json()["data"]["rejected"] == 1
    assert (await ack(s, new_auth, new_item)).json()["data"]["accepted"] == 1
    assert (await status(s)).json()["data"]["status"] == "Applied"


@pytest.mark.parametrize("fault", ["session", "token", "future_version", "camera", "zone", "worker", "tenant", "missing_key"])
async def test_ack_rejects_wrong_identity_and_policy(setup, monkeypatch, fault):
    s = setup
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    worker_id = None
    if fault == "session":
        auth["X-Worker-Session"] = str(uuid4())
    elif fault == "token":
        item["lease_token"] = str(uuid4())
    elif fault == "future_version":
        item["version"] = 999
    elif fault == "camera":
        item["camera_id"] = s.places[2].camera.public_id
    elif fault == "zone":
        item["zone_id"] = s.places[1].zone.public_id
    elif fault == "worker":
        worker_id = "another-worker"
    elif fault == "tenant":
        auth["X-Enterprise-Id"] = s.other.public_id
    else:
        auth.pop("X-Worker-Key")
    response = await ack(s, auth, item, worker_id)
    if fault in {"worker", "tenant", "missing_key"}:
        assert response.status_code in (401, 403)
    else:
        assert response.status_code == 200 and response.json()["data"]["accepted"] == 0
    assert (await status(s)).json()["data"]["status"] == "Pending"


async def test_status_is_scoped_and_old_confirmations_expire(setup, monkeypatch):
    s = setup
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    await ack(s, auth, item)
    assert (await status(s, "foreign")).status_code in (403, 404)
    assert (await status(s, "manager", s.places[1].zone.public_id)).status_code == 404
    assert (await status(s, "viewer")).status_code == 200
    async with AsyncSessionFactory() as db:
        await db.execute(update(CameraConfigApplication).where(CameraConfigApplication.camera_id == s.places[0].camera.id)
            .values(confirmed_at=func.now() - timedelta(seconds=91)))
        await db.commit()
    assert (await status(s)).json()["data"]["status"] == "Pending"


async def test_restore_enqueues_new_version_atomically(setup):
    s = setup
    await save(s)
    async with AsyncSessionFactory() as db:
        history = await db.scalar(select(ConfigHistory).where(ConfigHistory.zone_id == s.places[0].zone.id))
        result = await ConfigService(db).restore(s.places[0].zone.public_id, s.enterprise.public_id,
                                                history.public_id, s.users["admin"].public_id)
    job = await job_for(s)
    assert result["version"] == job.version == 3
    assert job.payload["config"]["required_ppe_types"] == ["helmet", "vest"]


async def test_disabled_camera_does_not_create_vacuous_applied_status(setup):
    await save(setup)
    async with AsyncSessionFactory() as db:
        await db.execute(update(Camera).where(Camera.id == setup.places[0].camera.id).values(status="Inactive"))
        await db.commit()
    report = (await status(setup)).json()["data"]
    assert report["status"] == "NoActiveCameras" and report["active_cameras"] == 0


async def test_confirmations_use_one_bulk_write_for_one_and_one_hundred_cameras(setup, monkeypatch):
    s = setup
    await save(s)
    place = s.places[0]
    async with AsyncSessionFactory() as db:
        db.add_all([Camera(enterprise_id=s.enterprise.id, factory_id=place.factory.id, zone_id=place.zone.id,
            name="Batch camera", code=uuid4().hex, rtsp_url="rtsp://example.invalid/feed") for _ in range(99)])
        await db.execute(update(AIWorker).where(AIWorker.id == s.worker.id).values(max_cameras=100))
        await db.commit()
    auth, _ = await make_ack(s, monkeypatch)
    async with AsyncSessionFactory() as db:
        rows = (await db.execute(select(Camera.public_id, CameraLease.token).join(
            CameraLease, CameraLease.camera_id == Camera.id).where(Camera.worker_id == s.worker.id))).all()
    items = [{"camera_id": camera_id, "zone_id": place.zone.public_id, "lease_token": token, "version": 2}
             for camera_id, token in rows]
    counts = []
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "INSERT")):
            statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        for size in (1, 100):
            statements.clear()
            response = await s.client.post(f"/api/v1/workers/{s.worker.worker_id}/config-applied", headers=auth,
                                           json={"applications": items[:size]})
            assert response.json()["data"]["accepted"] == size
            counts.append(len(statements))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert counts == [3, 3]  # Locked ownership read, database clock, bulk upsert.
    report = (await status(s)).json()["data"]
    assert report["status"] == "Applied" and report["applied_cameras"] == 100


async def test_startup_and_readiness_use_current_migration_and_require_dispatcher(setup):
    import json
    from src.modules.health.api.routes import readiness
    from src.shared.database.session import init_db
    await init_db()
    checks = json.loads((await readiness()).body)["data"]["checks"]
    assert checks["postgres"] == "ok"
    assert checks["config_delivery"] == "fail"  # This test app has no running background tasks.


@pytest.mark.skipif(not os.environ.get("TEST_CONFIG_BROKER"), reason="Requires local test RabbitMQ")
async def test_real_broker_confirmation_preserves_committed_event(setup, monkeypatch):
    import aio_pika
    import json
    await save(setup)
    job = await job_for(setup)
    connection = await aio_pika.connect_robust(os.environ.get("TEST_RABBITMQ_URL", settings.RABBITMQ_URL))
    try:
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange("config_test_" + uuid4().hex, aio_pika.ExchangeType.TOPIC, auto_delete=True)
        monkeypatch.setattr(publisher, "_exchange", exchange)
        # An offline worker has no queue. Broker acceptance still must not
        # claim application; its next HTTP reconciliation provides recovery.
        assert await ConfigDeliveryWorker().process_one(job.event_id)
        assert (await job_for(setup)).status == "Published"
        assert (await status(setup)).json()["data"]["status"] == "Pending"
        queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        await queue.bind(exchange, "config.zone_config_updated")
        await save(setup)
        job = await job_for(setup)
        assert await ConfigDeliveryWorker().process_one(job.event_id)
        message = await queue.get(timeout=5)
        assert json.loads(message.body) == job.payload
        assert message.message_id == job.event_id
        await message.ack()
        assert (await job_for(setup)).status == "Published"
    finally:
        await connection.close()
