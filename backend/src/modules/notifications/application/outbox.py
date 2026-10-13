"""PostgreSQL outbox with bounded sends and restart-safe delivery retries."""
import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
import random
from types import SimpleNamespace

from sqlalchemy import func, select
import structlog

from src.core.settings import settings
from src.modules.identity.infrastructure.repositories import UserRepository
from src.modules.realtime.manager import manager
from src.shared.database.models import (
    Alert, Camera, NotificationDelivery, NotificationLog, NotificationRecipient, User, Zone,
)
from src.shared.database.session import AsyncSessionFactory
from src.shared.email.sender import send_email
from src.shared.notify.channels import send_slack_alert, send_webhook_alert
from src.shared.security.resource_policy import scoped_query

log = structlog.get_logger()


async def enqueue_alert(db, alert, entity):
    """Only SQL here: caller owns commit of both alert and delivery records."""
    from src.modules.alerts.application.services import AlertService

    zone_name = await db.scalar(select(Zone.name).where(Zone.id == alert.zone_id))
    camera_code = await db.scalar(select(Camera.code).where(Camera.id == alert.camera_id))
    payload = {**AlertService.to_dict(entity), "alert_id": entity.id,
               "zone_name": zone_name, "camera_code": camera_code}
    # Convert timestamps to a JSON-safe representation before persisting.
    payload = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in payload.items()}
    recipients = []
    # Infrastructure-quality alerts retain their existing in-app-only policy.
    external = alert.alert_type != "CAMERA_SPEC_MISMATCH"
    if external:
        base = select(NotificationRecipient, User).join(User, User.id == NotificationRecipient.user_id).where(
            NotificationRecipient.enterprise_id == alert.enterprise_id,
            NotificationRecipient.deleted_at.is_(None), NotificationRecipient.is_active.is_(True),
            User.enterprise_id == alert.enterprise_id, User.deleted_at.is_(None), User.status == "Active",
        )
        recipients = (await db.execute(base.where(NotificationRecipient.zone_id == alert.zone_id))).all()
        if not recipients:
            recipients = (await db.execute(base.where(NotificationRecipient.zone_id.is_(None)))).all()

    def job(channel, recipient=None, configured=True):
        return NotificationDelivery(
            enterprise_id=alert.enterprise_id, alert_id=alert.id,
            recipient_id=recipient.id if recipient else None,
            delivery_key=f"{entity.id}:{channel}:{recipient.public_id if recipient else 'enterprise'}",
            channel=channel, payload=payload, max_attempts=settings.NOTIFY_RETRY_ATTEMPTS,
            status="Pending" if configured else "Skipped",
            last_error=None if configured else "not_configured",
        )

    # Duplicated recipient configuration must not duplicate email jobs.
    emails, desktop = {}, set()
    for recipient, user in recipients:
        if recipient.notify_email:
            emails[user.id] = user
        if recipient.notify_desktop:
            desktop.add(user.public_id)
    payload["notify_user_ids"] = sorted(desktop)
    db.add(job("realtime"))
    if external:
        db.add(job("slack", configured=bool(settings.SLACK_WEBHOOK_URL)))
        db.add(job("webhook", configured=bool(settings.ALERT_WEBHOOK_URL)))
        for user in emails.values():
            db.add(job("email", user, configured=bool(settings.SMTP_HOST)))
    await db.flush()


async def deliver(db, job):
    """One attempt; a provider accepting a message is not proof a human read it."""
    data = job.payload
    current_status = await db.scalar(select(Alert.status).where(
        Alert.id == job.alert_id, Alert.enterprise_id == job.enterprise_id))
    if current_status in {None, "Resolved", "FalsePositive"}:
        return "Skipped", "alert_closed_or_unavailable"
    if job.channel == "realtime":
        await manager.broadcast(data["enterprise_id"], {
            "type": "alert.created", "data": data, "event_id": job.public_id,
        })
        return "Published", None
    if job.channel == "slack":
        sent, reason = await send_slack_alert(data["alert_number"], data["alert_type"],
            data["severity"], data["zone_name"], data["camera_code"])
    elif job.channel == "webhook":
        sent, reason = await send_webhook_alert(data, delivery_id=job.public_id)
    elif job.channel == "email":
        user = await db.scalar(select(User).where(User.id == job.recipient_id,
            User.enterprise_id == job.enterprise_id, User.deleted_at.is_(None), User.status == "Active"))
        if not user or not user.email:
            return "Skipped", "recipient_unavailable"
        # Re-check current scope, including role/assignment changes since enqueue.
        account = await UserRepository(db).get_by_id(user.public_id)
        if account is None:
            return "Skipped", "recipient_unavailable"
        query = await scoped_query(db, select(Camera.id).where(
            Camera.public_id == data["camera_id"], Camera.enterprise_id == job.enterprise_id,
            Camera.deleted_at.is_(None)), Camera, user=SimpleNamespace(
                roles=account.roles, factory_id=account.factory_id, assigned_zone_ids=account.assigned_zone_ids))
        if await db.scalar(query) is None:
            return "Skipped", "recipient_out_of_scope"
        if not settings.SMTP_HOST:
            return "Skipped", "not_configured"
        subject = f"[{data['severity']}] Safety Alert {data['alert_number']}"
        body = "<h3>Safety Alert</h3>" + "".join(
            f"<p><b>{label}:</b> {escape(str(data[key]))}</p>" for label, key in
            [("Number", "alert_number"), ("Zone", "zone_name"), ("Camera", "camera_code"),
             ("Type", "alert_type"), ("Severity", "severity")])
        sent = await send_email(user.email, subject, body, message_id=f"<{job.public_id}@alerts.visionguard.ai>")
        reason = None if sent else "smtp_send_failed"
    else:
        return "Failed", "unknown_channel"
    if reason == "not_configured":
        return "Skipped", reason
    return ("Sent", None) if sent else ("Retrying", reason or "provider_send_failed")


class DeliveryWorker:
    def __init__(self):
        self.tasks = []

    def start(self):
        self.tasks = [asyncio.create_task(self.run()) for _ in range(settings.NOTIFY_WORKERS)]

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    async def run(self):
        while True:
            try:
                if await self.process_one():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Never log credential-bearing provider URLs or payloads.
                log.error("notifications.worker_failed", error_type=type(error).__name__)
            await asyncio.sleep(settings.NOTIFY_POLL_SECONDS)

    async def process_one(self, delivery_id=None):
        async with AsyncSessionFactory() as db, db.begin():
            query = select(NotificationDelivery).where(
                NotificationDelivery.status.in_(["Pending", "Retrying"]),
                NotificationDelivery.next_attempt_at <= func.now(),
            ).order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id).limit(1).with_for_update(skip_locked=True)
            if delivery_id:
                query = query.where(NotificationDelivery.public_id == delivery_id)
            job = await db.scalar(query)
            if job is None:
                return False
            # The row lock spans one bounded network attempt. A crash releases
            # it and rolls back, so another process can retry without leases.
            job.attempts += 1
            try:
                status, error = await asyncio.wait_for(deliver(db, job), settings.NOTIFY_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status, error = "Retrying", type(exc).__name__
            now = datetime.now(timezone.utc)
            if status == "Retrying":
                if job.attempts >= job.max_attempts:
                    status = "Failed"
                else:
                    delay = min(settings.NOTIFY_RETRY_MAX_SECONDS,
                        settings.NOTIFY_RETRY_BASE_SECONDS * 2 ** min(job.attempts - 1, 20))
                    job.next_attempt_at = now + timedelta(seconds=delay * random.uniform(0.8, 1.0))
            job.status = status
            job.last_error = error
            if status in {"Sent", "Published"}:
                job.delivered_at = now
            db.add(NotificationLog(enterprise_id=job.enterprise_id, alert_id=job.alert_id,
                recipient_id=job.recipient_id, channel=job.channel, status=status,
                failure_reason=error, retry_count=job.attempts - 1,
                sent_at=now if status in {"Sent", "Published"} else None))
        log.info("notifications.attempt", delivery_id=job.public_id, channel=job.channel,
                 status=status, attempt=job.attempts)
        return True


delivery_worker = DeliveryWorker()
