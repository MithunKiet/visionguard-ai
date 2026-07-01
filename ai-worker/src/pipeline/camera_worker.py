import asyncio
import structlog
import numpy as np
import cv2
from datetime import datetime, timezone

from src.pipeline.frame_reader import FrameReader
from src.pipeline.detector import PPEDetector
from src.pipeline.ppe_validator import PPEValidator
from src.events.publisher import publish
from src.config.settings import settings

log = structlog.get_logger()

CIRCUIT_BREAKER_THRESHOLD = 3   # AI Worker rule #6


class CameraWorker:

    def __init__(self, camera_id: str, rtsp_url: str, zone_config: dict,
                 enterprise_id: str, factory_id: str, zone_id: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.zone_config = zone_config
        self.enterprise_id = enterprise_id
        self.factory_id = factory_id
        self.zone_id = zone_id

        self._reader = FrameReader(camera_id, rtsp_url, zone_config.get("frame_sample_fps", 2))
        self._detector = PPEDetector()
        self._validator = PPEValidator()
        self._failure_count = 0
        self._isolated = False

    async def run(self) -> None:
        if self._isolated:
            log.error("camera_worker.isolated", camera_id=self.camera_id)
            return

        log.info("camera_worker.started", camera_id=self.camera_id)

        try:
            async for frame in self._reader.read_frames():
                await self._process_frame(frame)
        except Exception as e:
            self._failure_count += 1
            log.error("camera_worker.error", camera_id=self.camera_id, error=str(e),
                      failures=self._failure_count)

            if self._failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                self._isolated = True
                await publish("events.camera_offline_detected", {
                    "event": "camera_offline_detected",
                    "camera_id": self.camera_id,
                    "enterprise_id": self.enterprise_id,
                    "factory_id": self.factory_id,
                    "zone_id": self.zone_id,
                    "reason": "circuit_breaker_triggered",
                })
                log.error("camera_worker.circuit_breaker_open", camera_id=self.camera_id)

    async def _process_frame(self, frame: np.ndarray) -> None:
        detections = self._detector.detect(frame)
        violations = self._validator.evaluate(detections, self.zone_config)

        for v in violations:
            if v.get("review"):
                await publish("events.low_confidence_violation", {
                    "event": "low_confidence_violation",
                    "camera_id": self.camera_id,
                    "enterprise_id": self.enterprise_id,
                    "factory_id": self.factory_id,
                    "zone_id": self.zone_id,
                    **v,
                })
            else:
                snapshot_key = await self._capture_snapshot(frame, v["event"])
                await publish(f"events.{v['event']}", {
                    "event": v["event"],
                    "camera_id": self.camera_id,
                    "enterprise_id": self.enterprise_id,
                    "factory_id": self.factory_id,
                    "zone_id": self.zone_id,
                    "confidence": v["confidence"],
                    "snapshot_key": snapshot_key,
                    "config_version": self.zone_config.get("version", 1),
                })

    async def _capture_snapshot(self, frame: np.ndarray, event_name: str) -> str:
        from minio import Minio
        import io
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        key = f"{self.enterprise_id}/{self.factory_id}/{self.zone_id}/{self.camera_id}/{ts}_{event_name}.jpg"

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        minio = Minio(settings.MINIO_ENDPOINT,
                      access_key=settings.MINIO_ACCESS_KEY,
                      secret_key=settings.MINIO_SECRET_KEY,
                      secure=False)

        minio.put_object(
            settings.MINIO_BUCKET_SNAPSHOTS,
            key,
            data=io.BytesIO(buf.tobytes()),
            length=len(buf),
            content_type="image/jpeg",
        )
        return key
