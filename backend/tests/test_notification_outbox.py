"""Durable delivery regressions; all outbound channels are mocked."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import os
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from tests.test_review_integration import setup as integration_setup, event, headers
from src.core.settings import settings
from src.modules.notifications.application import outbox
from src.shared.database.models import Alert, AuditLog, EventReceipt, NotificationDelivery, NotificationLog, NotificationRecipient, PPEViolation, User
from src.shared.database.session import AsyncSessionFactory
from src.shared.messaging.consumer import _dispatch_event, _route_event

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable database and Redis")
setup = integration_setup


@pytest.fixture(autouse=True)
def channels(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setattr(settings, "SLACK_WEBHOOK_URL", "https://slack.example.invalid/secret")
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "https://webhook.example.invalid/secret")
    result = SimpleNamespace(email=AsyncMock(return_value=True), slack=AsyncMock(return_value=(True, None)),
                             webhook=AsyncMock(return_value=(True, None)), realtime=AsyncMock())
    monkeypatch.setattr(outbox, "send_email", result.email)
    monkeypatch.setattr(outbox, "send_slack_alert", result.slack)
    monkeypatch.setattr(outbox, "send_webhook_alert", result.webhook)
    monkeypatch.setattr(outbox.manager, "broadcast", result.realtime)
    return result


async def generate(s, routing_key="events.helmet_missing_detected"):
    async with AsyncSessionFactory() as db:
        # Duplicate configuration intentionally exercises email deduplication.
        for _ in range(2):
            db.add(NotificationRecipient(enterprise_id=s.enterprise.id, zone_id=s.places[0].zone.id,
                user_id=s.users["viewer"].id, notify_email=True, notify_desktop=True))
        await db.commit()
    payload = event(s)
    await _route_event(routing_key, payload)
    return payload, await jobs(s)


async def jobs(s):
    async with AsyncSessionFactory() as db:
        rows = (await db.scalars(select(NotificationDelivery).where(NotificationDelivery.enterprise_id == s.enterprise.id))).all()
        return {row.channel: row for row in rows}


async def make_due(job):
    async with AsyncSessionFactory() as db:
        await db.execute(update(NotificationDelivery).where(NotificationDelivery.id == job.id).values(
            next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()


@pytest.mark.parametrize("routing_key,expected", [
    ("events.helmet_missing_detected", {"email", "slack", "webhook", "realtime"}),
    ("events.overcrowding_detected", {"email", "slack", "webhook", "realtime"}),
    ("events.camera_spec_mismatch", {"realtime"}),
])
async def test_alert_and_jobs_are_atomic_and_event_replay_is_idempotent(setup, channels, routing_key, expected):
    s = setup
    payload, queued = await generate(s, routing_key)
    await _route_event(routing_key, payload)
    assert set(queued) == expected
    assert all(row.status == "Pending" and row.attempts == 0 for row in queued.values())
    channels.email.assert_not_awaited()
    channels.slack.assert_not_awaited()
    channels.webhook.assert_not_awaited()
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(Alert).where(Alert.enterprise_id == s.enterprise.id)) == 1
        assert await db.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.enterprise_id == s.enterprise.id)) == len(expected)
        assert await db.get(EventReceipt, payload["event_id"]) is not None


async def test_enqueue_failure_rolls_back_receipt_violation_alert_and_jobs(setup, monkeypatch):
    s = setup
    original = outbox.enqueue_alert
    async def fail_after_enqueue(*args):
        await original(*args)
        raise RuntimeError("Injected outbox failure")
    monkeypatch.setattr(outbox, "enqueue_alert", fail_after_enqueue)
    payload = event(s)
    with pytest.raises(RuntimeError, match="Injected"):
        await _route_event("events.helmet_missing_detected", payload)
    async with AsyncSessionFactory() as db:
        assert await db.get(EventReceipt, payload["event_id"]) is None
        for model in [Alert, PPEViolation, NotificationDelivery]:
            assert await db.scalar(select(func.count()).select_from(model).where(model.enterprise_id == s.enterprise.id)) == 0


async def test_retry_survives_new_worker_without_resending_successful_channels(setup, channels):
    s = setup
    _, queued = await generate(s)
    channels.email.side_effect = [False, True]
    worker = outbox.DeliveryWorker()
    for job in queued.values():
        assert await worker.process_one(job.public_id)
    first = await jobs(s)
    assert first["email"].status == "Retrying" and first["email"].delivered_at is None
    assert first["slack"].status == first["webhook"].status == "Sent"
    assert first["realtime"].status == "Published"
    assert not await worker.process_one(queued["email"].public_id)  # Backoff is persisted.
    await make_due(queued["email"])
    assert await outbox.DeliveryWorker().process_one(queued["email"].public_id)
    final = await jobs(s)
    assert final["email"].status == "Sent" and final["email"].attempts == 2
    for channel in ["slack", "webhook", "realtime"]:
        assert not await worker.process_one(queued[channel].public_id)
    channels.slack.assert_awaited_once()
    channels.webhook.assert_awaited_once()
    assert channels.email.await_args_list[0].kwargs["message_id"] == channels.email.await_args_list[1].kwargs["message_id"]
    async with AsyncSessionFactory() as db:
        logs = (await db.scalars(select(NotificationLog).where(NotificationLog.alert_id == queued["email"].alert_id,
            NotificationLog.channel == "email").order_by(NotificationLog.id))).all()
        assert [row.status for row in logs] == ["Retrying", "Sent"]
        assert logs[0].sent_at is None and logs[1].sent_at is not None


async def test_concurrent_worker_skips_lock_and_cancelled_send_recovers(setup, channels):
    _, queued = await generate(setup)
    started = asyncio.Event()
    async def interrupted_send(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
    channels.email.side_effect = interrupted_send
    worker = outbox.DeliveryWorker()
    task = asyncio.create_task(worker.process_one(queued["email"].public_id))
    try:
        await asyncio.wait_for(started.wait(), 3)
        assert not await outbox.DeliveryWorker().process_one(queued["email"].public_id)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    pending = (await jobs(setup))["email"]
    assert pending.status == "Pending" and pending.attempts == 0
    channels.email.side_effect = None
    assert await outbox.DeliveryWorker().process_one(pending.public_id)
    assert (await jobs(setup))["email"].status == "Sent"


async def test_crash_after_provider_acceptance_reuses_delivery_identity(setup, channels, monkeypatch):
    _, queued = await generate(setup)
    original = outbox.deliver
    async def accepted_then_crashed(*args):
        assert await original(*args) == ("Sent", None)
        raise asyncio.CancelledError
    monkeypatch.setattr(outbox, "deliver", accepted_then_crashed)
    with pytest.raises(asyncio.CancelledError):
        await outbox.DeliveryWorker().process_one(queued["webhook"].public_id)
    assert (await jobs(setup))["webhook"].status == "Pending"
    monkeypatch.setattr(outbox, "deliver", original)
    assert await outbox.DeliveryWorker().process_one(queued["webhook"].public_id)
    assert channels.webhook.await_count == 2
    assert channels.webhook.await_args_list[0].kwargs["delivery_id"] == channels.webhook.await_args_list[1].kwargs["delivery_id"]


async def test_failed_jobs_visible_and_replay_is_tenant_admin_only(setup, channels, monkeypatch):
    monkeypatch.setattr(settings, "NOTIFY_RETRY_ATTEMPTS", 1)
    s = setup
    _, queued = await generate(s)
    channels.webhook.return_value = (False, "http_503")
    assert await outbox.DeliveryWorker().process_one(queued["webhook"].public_id)
    path = f"/api/v1/notifications/deliveries/{queued['webhook'].public_id}/retry"
    assert (await s.client.post(path, headers=headers(s, "foreign"))).status_code == 404
    assert (await s.client.post(path, headers=headers(s, "manager"))).status_code == 403
    listed = await s.client.get("/api/v1/notifications/deliveries?status=Failed", headers=headers(s))
    assert listed.status_code == 200 and listed.json()["meta"]["total"] == 1
    assert listed.json()["data"][0]["last_error"] == "http_503"
    foreign = await s.client.get("/api/v1/notifications/deliveries", headers=headers(s, "foreign"))
    assert foreign.json()["data"] == []
    assert (await s.client.post(path, headers=headers(s))).status_code == 200
    assert (await s.client.post(path, headers=headers(s))).status_code == 409
    channels.webhook.return_value = (True, None)
    assert await outbox.DeliveryWorker().process_one(queued["webhook"].public_id)
    assert (await s.client.post(path, headers=headers(s))).status_code == 409
    assert (await jobs(s))["webhook"].attempts == 2
    assert channels.webhook.await_args_list[0].kwargs["delivery_id"] == channels.webhook.await_args_list[1].kwargs["delivery_id"]
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.enterprise_id == s.enterprise.id,
            AuditLog.action == "NOTIFICATION_RETRY_REQUESTED")) == 1


@pytest.mark.parametrize("change,reason", [("suspended", "recipient_unavailable"), ("scope", "recipient_out_of_scope"), ("closed", "alert_closed_or_unavailable")])
async def test_delayed_jobs_respect_current_user_scope_and_closed_alerts(setup, channels, change, reason):
    s = setup
    _, queued = await generate(s)
    async with AsyncSessionFactory() as db:
        if change == "closed":
            await db.execute(update(Alert).where(Alert.id == queued["email"].alert_id).values(status="FalsePositive"))
        else:
            values = {"status": "Inactive"} if change == "suspended" else {"factory_id": None, "assigned_zone_ids": []}
            await db.execute(update(User).where(User.id == s.users["viewer"].id).values(**values))
        await db.commit()
    assert await outbox.DeliveryWorker().process_one(queued["email"].public_id)
    job = (await jobs(s))["email"]
    assert job.status == "Skipped" and job.last_error == reason
    channels.email.assert_not_awaited()


async def test_unconfigured_channel_can_be_replayed_after_configuration(setup, channels, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    _, queued = await generate(setup)
    assert queued["email"].status == "Skipped"
    assert not await outbox.DeliveryWorker().process_one(queued["email"].public_id)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.invalid")
    path = f"/api/v1/notifications/deliveries/{queued['email'].public_id}/retry"
    assert (await setup.client.post(path, headers=headers(setup))).status_code == 200
    assert await outbox.DeliveryWorker().process_one(queued["email"].public_id)
    channels.email.assert_awaited_once()


async def test_delivery_timeout_is_persisted_as_retry(setup, channels, monkeypatch):
    _, queued = await generate(setup)
    monkeypatch.setattr(settings, "NOTIFY_TIMEOUT_SECONDS", 0.02)
    async def hang(*args, **kwargs):
        await asyncio.Event().wait()
    channels.slack.side_effect = hang
    assert await outbox.DeliveryWorker().process_one(queued["slack"].public_id)
    job = (await jobs(setup))["slack"]
    assert job.status == "Retrying" and job.last_error == "TimeoutError"


async def test_database_outage_requeues_original_broker_message():
    message = SimpleNamespace(body=b'{"event_id": "same-id"}', routing_key="events.helmet_missing_detected", nack=AsyncMock())
    @asynccontextmanager
    async def process(**kwargs):
        assert kwargs == {"requeue": False, "ignore_processed": True}
        yield
    message.process = process
    with patch("src.shared.messaging.consumer._route_event", new=AsyncMock(side_effect=OperationalError("test", {}, Exception()))), patch("asyncio.sleep", new=AsyncMock()):
        await _dispatch_event(message)
    message.nack.assert_awaited_once_with(requeue=True)
    message.nack.reset_mock()
    with patch("src.shared.messaging.consumer._route_event", new=AsyncMock(side_effect=ValueError("Invalid event"))):
        with pytest.raises(ValueError):
            await _dispatch_event(message)
    message.nack.assert_not_awaited()


@pytest.mark.skipif(not os.environ.get("TEST_RABBITMQ_URL"), reason="Requires isolated test queues on RabbitMQ")
async def test_real_broker_redelivery_and_dead_letter_preserve_events(setup, monkeypatch):
    import aio_pika
    from src.shared.messaging import consumer

    connection = await aio_pika.connect_robust(os.environ["TEST_RABBITMQ_URL"])
    channel = await connection.channel()
    queue_name = "test.outbox." + uuid4().hex
    dead_letter = await channel.declare_queue(queue_name + ".dlq", durable=True)
    queue = await channel.declare_queue(queue_name, durable=True, arguments={
        "x-dead-letter-exchange": "", "x-dead-letter-routing-key": dead_letter.name,
    })
    finished = asyncio.Event()
    attempts = []
    original = consumer._route_event
    payload = event(setup)
    async def route(_key, body):
        attempts.append(body["event_id"])
        if len(attempts) == 1:
            raise OperationalError("injected database outage", {}, Exception())
        await original("events.helmet_missing_detected", body)
    monkeypatch.setattr(consumer, "_route_event", route)
    async def callback(message):
        try:
            await consumer._dispatch_event(message)
            if len(attempts) >= 2:
                finished.set()
        except (ValueError, KeyError):
            pass  # process() has already rejected the poison message to DLQ.
    try:
        await queue.consume(callback)
        await channel.default_exchange.publish(aio_pika.Message(body=json.dumps(payload).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=queue.name)
        await asyncio.wait_for(finished.wait(), 10)
        assert attempts == [payload["event_id"], payload["event_id"]]
        assert set(await jobs(setup)) == {"slack", "webhook", "realtime"}
        await channel.default_exchange.publish(aio_pika.Message(body=b'{"invalid": true}',
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=queue.name)
        async with dead_letter.iterator() as messages:
            message = await asyncio.wait_for(anext(messages), 5)
            assert json.loads(message.body) == {"invalid": True}
            await message.ack()
    finally:
        await queue.delete(if_unused=False, if_empty=False)
        await dead_letter.delete(if_unused=False, if_empty=False)
        await connection.close()
