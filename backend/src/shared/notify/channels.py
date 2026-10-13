"""
Outbound notification channels beyond email: Slack incoming webhook and a
generic JSON webhook. Both are enterprise-infrastructure level (configured
via env, not per-user) and degrade to logging when unconfigured — same
pattern as the SMTP sender.

Each call performs one bounded attempt. Durable retry scheduling is owned by
the PostgreSQL notification outbox.
"""
import httpx
import structlog

from src.core.settings import settings

log = structlog.get_logger()

async def _post_once(url: str, payload: dict, channel: str, delivery_id: str | None = None) -> tuple[bool, str | None]:
    """Do not persist/log URLs: webhook URLs frequently contain credentials."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload,
                headers={"Idempotency-Key": delivery_id} if delivery_id else {})
            response.raise_for_status()
        return True, None
    except httpx.HTTPStatusError as error:
        reason = f"http_{error.response.status_code}"
    except Exception as error:
        reason = type(error).__name__
    log.warning(f"{channel}.send_failed", error_type=reason)
    return False, reason


async def send_slack_alert(
    alert_number: str, alert_type: str, severity: str, zone_name: str, camera_code: str,
) -> tuple[bool, str | None]:
    if not settings.SLACK_WEBHOOK_URL:
        log.info("slack.would_send", alert=alert_number, note="SLACK_WEBHOOK_URL not configured — logging only")
        return False, "not_configured"

    severity_emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵"}
    payload = {
        "text": f"{severity_emoji.get(severity, '⚪')} *[{severity}] Safety Alert {alert_number}*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{severity_emoji.get(severity, '⚪')} *[{severity}] Safety Alert {alert_number}*\n"
                        f"*Type:* {alert_type}\n"
                        f"*Zone:* {zone_name}\n"
                        f"*Camera:* {camera_code}\n"
                        f"Log in to VisionGuard AI to acknowledge and resolve."
                    ),
                },
            }
        ],
    }
    return await _post_once(settings.SLACK_WEBHOOK_URL, payload, "slack")


async def send_webhook_alert(alert_payload: dict, *, delivery_id: str | None = None) -> tuple[bool, str | None]:
    if not settings.ALERT_WEBHOOK_URL:
        return False, "not_configured"
    return await _post_once(
        settings.ALERT_WEBHOOK_URL,
        {"event": "alert.created", "delivery_id": delivery_id, "alert": alert_payload},
        "webhook", delivery_id,
    )
