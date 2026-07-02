"""
SMTP email sender. If SMTP_HOST is unset, emails are logged instead of sent
— lets the notification pipeline run end-to-end in dev/demo without a real
mail server configured.
"""
import aiosmtplib
import structlog
from email.mime.text import MIMEText

from src.core.settings import settings

log = structlog.get_logger()


async def send_email(to: str, subject: str, body_html: str) -> bool:
    if not settings.SMTP_HOST:
        log.info("email.would_send", to=to, subject=subject, note="SMTP_HOST not configured — logging only")
        return False

    message = MIMEText(body_html, "html")
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_USE_TLS,
        )
        log.info("email.sent", to=to, subject=subject)
        return True
    except Exception as e:
        log.error("email.send_failed", to=to, subject=subject, error=str(e))
        return False
