"""
Outbound notification channels beyond email: Slack incoming webhook and a
generic JSON webhook. Both are enterprise-infrastructure level (configured
via env, not per-user) and degrade to logging when unconfigured — same
pattern as the SMTP sender.

Every send retries up to NOTIFY_RETRY_ATTEMPTS with a short backoff before
reporting failure, so a transient network blip doesn't drop an alert.
"""
import asyncio

import httpx
import structlog

from src.core.settings import settings

log = structlog.get_logger()

_RETRY_BACKOFF_SECONDS = 2.0


async def _post_with_retry(url: str, payload: dict, channel: str) -> tuple[bool, str | None]:
    """Returns (sent, failure_reason)."""
    last_error: str | None = None
    for attempt in range(1, settings.NOTIFY_RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            log.info(f"{channel}.sent", attempt=attempt)
            return True, None
        except Exception as e:
            last_error = str(e)
            log.warning(f"{channel}.send_failed", attempt=attempt, error=last_error)
            if attempt < settings.NOTIFY_RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    return False, last_error


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
    return await _post_with_retry(settings.SLACK_WEBHOOK_URL, payload, "slack")


async def send_webhook_alert(alert_payload: dict) -> tuple[bool, str | None]:
    if not settings.ALERT_WEBHOOK_URL:
        return False, "not_configured"
    return await _post_with_retry(
        settings.ALERT_WEBHOOK_URL,
        {"event": "alert.created", "alert": alert_payload},
        "webhook",
    )
