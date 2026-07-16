"""
Roboflow hosted-inference client for Option B (community-trained PPE model,
no local fine-tuning yet). Called synchronously from PPEDetector.detect_batch,
which already runs off the event loop via asyncio.to_thread — a blocking
httpx call here doesn't stall the worker's asyncio loop.

REST contract (detect.roboflow.com only serves v1 routes):
    POST {ROBOFLOW_API_URL}/{ROBOFLOW_MODEL_ID}?api_key=...&confidence=...
    body: base64-encoded JPEG, Content-Type: application/x-www-form-urlencoded
    -> {"predictions": [{"x", "y", "width", "height", "class", "confidence"}, ...]}
    (x, y is the box CENTER in pixels, not top-left.)
"""
import base64

import cv2
import httpx
import numpy as np
import structlog

from src.config.settings import settings

log = structlog.get_logger()


class RoboflowPPEClient:

    def __init__(self):
        self._client = httpx.Client(timeout=settings.ROBOFLOW_TIMEOUT_SECONDS)
        self._url = f"{settings.ROBOFLOW_API_URL}/{settings.ROBOFLOW_MODEL_ID}"

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Returns raw Roboflow predictions for one frame, or [] on any
        failure (network/quota/timeout) — a remote outage degrades to "no
        items detected" rather than crashing the camera's processing loop."""
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            return []
        b64 = base64.b64encode(buf).decode("ascii")
        try:
            resp = self._client.post(
                self._url,
                params={
                    "api_key": settings.ROBOFLOW_API_KEY,
                    "confidence": int(settings.ROBOFLOW_CONFIDENCE * 100),
                },
                data=b64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json().get("predictions", [])
        except Exception as e:
            log.warning("remote_ppe.detect_failed", error=str(e))
            return []

    def close(self) -> None:
        self._client.close()
