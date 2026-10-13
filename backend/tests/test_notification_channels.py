"""Transport contract tests; no requests leave the process."""
from unittest.mock import AsyncMock, patch

import httpx

from src.core.settings import settings
from src.shared.notify.channels import send_webhook_alert
from src.shared.email.sender import send_email


async def test_webhook_retries_keep_idempotency_header_and_payload(monkeypatch):
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "https://example.invalid/secret-token")
    request = httpx.Request("POST", settings.ALERT_WEBHOOK_URL)
    client = AsyncMock()
    client.post.side_effect = [httpx.Response(503, request=request), httpx.Response(200, request=request)]
    with patch("src.shared.notify.channels.httpx.AsyncClient") as factory:
        factory.return_value.__aenter__.return_value = client
        assert await send_webhook_alert({"alert_id": "alert"}, delivery_id="delivery") == (False, "http_503")
        assert await send_webhook_alert({"alert_id": "alert"}, delivery_id="delivery") == (True, None)
    assert client.post.await_count == 2
    for call in client.post.await_args_list:
        assert call.kwargs["headers"] == {"Idempotency-Key": "delivery"}
        assert call.kwargs["json"]["delivery_id"] == "delivery"


async def test_smtp_uses_stable_message_id_and_timeout(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.invalid")
    with patch("src.shared.email.sender.aiosmtplib.send", new=AsyncMock()) as smtp:
        for _ in range(2):
            assert await send_email("test@example.com", "Safety alert", "<p>Test</p>", message_id="<delivery@example.invalid>")
    for call in smtp.await_args_list:
        assert call.args[0]["Message-ID"] == "<delivery@example.invalid>"
        assert call.kwargs["timeout"] == 10
