"""
NotificationService — resolve who to notify for a zone violation/alert and
send email + collect desktop-notification targets.
"""
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.domain.entities import NotificationRecipientEntity
from src.modules.notifications.infrastructure.repositories import NotificationRecipientRepository
from src.shared.database.models import Camera, User, Zone
from src.shared.email.sender import send_email

log = structlog.get_logger()


class NotificationService:

    def __init__(self, repo: NotificationRecipientRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    # ── Recipient config CRUD ───────────────────────────────────────────────

    async def list_recipients(self, enterprise_id: UUID, zone_id: UUID | None = None) -> list[dict]:
        recipients = await self._repo.list(enterprise_id, zone_id)
        return [self._to_dict(r) for r in recipients]

    async def add_recipient(
        self, enterprise_id: UUID, user_id: UUID, zone_id: UUID | None,
        level: int, notify_email: bool, notify_desktop: bool,
    ) -> dict:
        import uuid
        entity = NotificationRecipientEntity(
            id=uuid.uuid4(), enterprise_id=enterprise_id, zone_id=zone_id,
            user_id=user_id, level=level, notify_email=notify_email, notify_desktop=notify_desktop,
        )
        return self._to_dict(await self._repo.create(entity))

    async def remove_recipient(self, recipient_id: UUID, enterprise_id: UUID) -> None:
        await self._repo.delete(recipient_id, enterprise_id)

    # ── Called when an alert is created ─────────────────────────────────────

    async def notify_zone_violation(
        self, enterprise_id: UUID, zone_id: UUID, camera_id: UUID, alert_id: UUID,
        alert_number: str, alert_type: str, severity: str,
    ) -> list[str]:
        """
        Emails + logs delivery for every configured recipient of this zone
        (falling back to enterprise-wide recipients if none are zone-specific).
        Returns the user_ids that should get a desktop notification, so the
        caller can include them in the WebSocket broadcast payload.
        """
        recipients = await self._repo.list_for_zone_with_fallback(enterprise_id, zone_id)
        if not recipients:
            return []

        zone = (await self._db.execute(select(Zone).where(Zone.id == zone_id))).scalar_one_or_none()
        camera = (await self._db.execute(select(Camera).where(Camera.id == camera_id))).scalar_one_or_none()
        zone_name = zone.name if zone else "Unknown zone"
        camera_code = camera.code if camera else "Unknown camera"

        desktop_targets: list[str] = []
        subject = f"[{severity}] {alert_type.replace('PPE_VIOLATION_', '').replace('_', ' ').title()} — {zone_name}"
        body = (
            f"<h3>Safety Alert {alert_number}</h3>"
            f"<p><b>Zone:</b> {zone_name}<br>"
            f"<b>Camera:</b> {camera_code}<br>"
            f"<b>Type:</b> {alert_type}<br>"
            f"<b>Severity:</b> {severity}</p>"
            f"<p>Log in to VisionGuard AI to acknowledge and resolve this alert.</p>"
        )

        for recipient in recipients:
            user = (await self._db.execute(
                select(User).where(User.id == recipient.user_id)
            )).scalar_one_or_none()
            if not user or not user.email:
                continue

            if recipient.notify_email:
                sent = await send_email(user.email, subject, body)
                await self._repo.log_delivery(
                    enterprise_id, alert_id, recipient.user_id, "email",
                    "Sent" if sent else "Skipped",
                )

            if recipient.notify_desktop:
                desktop_targets.append(str(recipient.user_id))
                await self._repo.log_delivery(enterprise_id, alert_id, recipient.user_id, "desktop", "Sent")

        return desktop_targets

    @staticmethod
    def _to_dict(r: NotificationRecipientEntity) -> dict:
        return {
            "id": str(r.id),
            "enterprise_id": str(r.enterprise_id),
            "zone_id": str(r.zone_id) if r.zone_id else None,
            "user_id": str(r.user_id),
            "level": r.level,
            "notify_email": r.notify_email,
            "notify_desktop": r.notify_desktop,
        }
