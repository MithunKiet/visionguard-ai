import asyncio
import time
import structlog
import numpy as np
import cv2
from datetime import datetime, timezone
from minio import Minio

from src.pipeline.frame_reader import FrameReader
from src.pipeline.batch_detector import BatchDetector
from src.pipeline.ppe_validator import PPEValidator
from src.events.publisher import publish
from src.config.settings import settings
from src.health.metrics import frames_processed_total, violations_detected_total

log = structlog.get_logger()

CIRCUIT_BREAKER_THRESHOLD = 3   # AI Worker rule #6

# Occupancy publishing cadence: publish when the person count changes but at
# most once per OCCUPANCY_MIN_INTERVAL_SECONDS (a count bouncing 3↔4 every
# frame would otherwise flood RabbitMQ and the dashboard feed), and at least
# every OCCUPANCY_HEARTBEAT_SECONDS while it's stable so the dashboard never
# goes stale.
OCCUPANCY_MIN_INTERVAL_SECONDS = 5
OCCUPANCY_HEARTBEAT_SECONDS = 30
OVERCROWDING_COOLDOWN_SECONDS = 120

# A degraded feed (bad NVR transcode, network throttling, wrong lens) rarely
# recovers within minutes, so re-alerting every processed frame would just
# spam the same fact — recheck at most this often per connection.
SPEC_MISMATCH_COOLDOWN_SECONDS = 600

# Shared across all CameraWorker instances in this process — one client
# connection reused for every snapshot upload instead of reconnecting per call.
_minio = Minio(settings.MINIO_ENDPOINT,
               access_key=settings.MINIO_ACCESS_KEY,
               secret_key=settings.MINIO_SECRET_KEY,
               secure=False)


class CameraWorker:

    def __init__(self, camera_id: str, rtsp_url: str, zone_config: dict,
                 enterprise_id: str, factory_id: str, zone_id: str, detector: BatchDetector,
                 active: bool = True):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.zone_config = zone_config
        self.enterprise_id = enterprise_id
        self.factory_id = factory_id
        self.zone_id = zone_id
        # Manual on/off toggle (hot-applied via config_events, see zone_sync.py).
        # The RTSP connection stays open and frames keep being read even when
        # off, so turning back on is instant — no reconnect needed.
        self._active = active

        self._reader = FrameReader(camera_id, rtsp_url, zone_config.get("frame_sample_fps", 2))
        # Shared BatchDetector, one per process — every camera on this
        # worker submits frames to it so inference can run in batches
        # instead of each camera loading its own model copy and calling
        # inference one image at a time.
        self._detector = detector
        self._validator = PPEValidator()
        self._failure_count = 0
        self._isolated = False
        self._last_occupancy_count: int | None = None
        self._last_occupancy_published = 0.0
        self._last_overcrowding_fired = 0.0
        self._last_spec_check = 0.0
        self._spec_mismatch_active = False

    def set_active(self, active: bool) -> None:
        self._active = active
        log.info("camera_worker.active_changed", camera_id=self.camera_id, active=active)

    def apply_zone_config(self, new_config: dict) -> None:
        """Hot-swap zone config (rule #8) — takes effect on the next frame.
        Frame sampling rate is pushed down into the reader immediately."""
        self.zone_config = new_config
        fps = new_config.get("frame_sample_fps")
        if fps:
            self._reader.set_sample_fps(fps)

    async def run(self) -> None:
        if self._isolated:
            log.error("camera_worker.isolated", camera_id=self.camera_id)
            return

        log.info("camera_worker.started", camera_id=self.camera_id)

        # Retries the frame loop on failure (a fresh FrameReader.read_frames()
        # generator each time, so RTSP reconnects from scratch too) up to
        # CIRCUIT_BREAKER_THRESHOLD consecutive failures — a single transient
        # error (e.g. a GPU hiccup) must not permanently kill this camera
        # while the worker process keeps running.
        while not self._isolated:
            try:
                async for frame in self._reader.read_frames():
                    await self._process_frame(frame)
                    self._failure_count = 0
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
                    return

                await asyncio.sleep(5)

    async def _process_frame(self, frame: np.ndarray) -> None:
        if not self._active:
            # Turned off — drop the frame with zero GPU/CPU work. The RTSP
            # read loop above keeps running so the stream stays connected
            # and turning back on is instant.
            return

        # Submits to the shared BatchDetector, which groups this frame with
        # whatever other cameras submit within the same short window and
        # runs one batched GPU inference call for all of them — cheaper per
        # camera than each running its own single-image call, and never
        # blocks this worker's event loop (inference itself runs in a
        # thread inside BatchDetector).
        await self._check_camera_spec()

        detections = await self._detector.detect(frame, camera_id=self.camera_id)
        frames_processed_total.labels(camera_id=self.camera_id).inc()
        violations = self._validator.evaluate(detections, self.zone_config)

        await self._publish_occupancy(detections)

        for v in violations:
            violations_detected_total.labels(camera_id=self.camera_id, violation_type=v["event"]).inc()
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

    async def _publish_occupancy(self, detections: list) -> None:
        """Person count per frame → occupancy_updated on change or heartbeat,
        overcrowding_detected when the count exceeds the zone capacity."""
        person_threshold = self.zone_config.get("person_threshold", 0.70)
        count = sum(
            1 for d in detections
            if d.class_name == "person" and d.confidence >= person_threshold
        )

        now = time.monotonic()
        elapsed = now - self._last_occupancy_published
        changed = count != self._last_occupancy_count
        stale = elapsed >= OCCUPANCY_HEARTBEAT_SECONDS
        if (changed and elapsed >= OCCUPANCY_MIN_INTERVAL_SECONDS) or stale:
            self._last_occupancy_count = count
            self._last_occupancy_published = now
            await publish("events.occupancy_updated", {
                "event": "occupancy_updated",
                "camera_id": self.camera_id,
                "enterprise_id": self.enterprise_id,
                "factory_id": self.factory_id,
                "zone_id": self.zone_id,
                "count": count,
            })

        max_occupancy = self.zone_config.get("max_occupancy")
        if (
            max_occupancy
            and count > max_occupancy
            and (now - self._last_overcrowding_fired) >= OVERCROWDING_COOLDOWN_SECONDS
        ):
            self._last_overcrowding_fired = now
            await publish("events.overcrowding_detected", {
                "event": "overcrowding_detected",
                "camera_id": self.camera_id,
                "enterprise_id": self.enterprise_id,
                "factory_id": self.factory_id,
                "zone_id": self.zone_id,
                "count": count,
                "max_occupancy": max_occupancy,
            })
            log.warning("camera_worker.overcrowding", camera_id=self.camera_id,
                        count=count, max_occupancy=max_occupancy)

    async def _check_camera_spec(self) -> None:
        """Compare the connected stream's actual fps/resolution to the
        mandatory install spec (Section 18: min 1080p @ 15 FPS). A stream
        can stay "connected" while quietly degrading — bad NVR transcode,
        network throttling, wrong lens — which FrameReader's own reconnect
        logic never catches, since the stream never actually drops."""
        now = time.monotonic()
        if (now - self._last_spec_check) < SPEC_MISMATCH_COOLDOWN_SECONDS:
            return
        self._last_spec_check = now

        fps = self._reader.stream_fps
        width = self._reader.stream_width
        height = self._reader.stream_height
        if fps is None or width is None or height is None:
            return

        fps_ok = fps >= settings.MIN_EXPECTED_FPS
        resolution_ok = width >= settings.MIN_EXPECTED_WIDTH and height >= settings.MIN_EXPECTED_HEIGHT

        if fps_ok and resolution_ok:
            if self._spec_mismatch_active:
                log.info("camera_worker.spec_recovered", camera_id=self.camera_id,
                          fps=fps, resolution=f"{width}x{height}")
                self._spec_mismatch_active = False
            return

        self._spec_mismatch_active = True
        log.warning("camera_worker.spec_mismatch", camera_id=self.camera_id,
                    actual_fps=fps, actual_resolution=f"{width}x{height}",
                    expected_fps=settings.MIN_EXPECTED_FPS,
                    expected_resolution=f"{settings.MIN_EXPECTED_WIDTH}x{settings.MIN_EXPECTED_HEIGHT}")
        await publish("events.camera_spec_mismatch", {
            "event": "camera_spec_mismatch",
            "camera_id": self.camera_id,
            "enterprise_id": self.enterprise_id,
            "factory_id": self.factory_id,
            "zone_id": self.zone_id,
            "actual_fps": fps,
            "actual_width": width,
            "actual_height": height,
            "expected_fps": settings.MIN_EXPECTED_FPS,
            "expected_width": settings.MIN_EXPECTED_WIDTH,
            "expected_height": settings.MIN_EXPECTED_HEIGHT,
        })

    async def _capture_snapshot(self, frame: np.ndarray, event_name: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        key = f"{self.enterprise_id}/{self.factory_id}/{self.zone_id}/{self.camera_id}/{ts}_{event_name}.jpg"
        # JPEG encode + the MinIO PUT are both blocking I/O — same reasoning
        # as detect() above, offload so this camera's upload doesn't stall
        # every other camera on this worker.
        await asyncio.to_thread(self._upload_snapshot, frame, key)
        return key

    def _upload_snapshot(self, frame: np.ndarray, key: str) -> None:
        import io
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        _minio.put_object(
            settings.MINIO_BUCKET_SNAPSHOTS,
            key,
            data=io.BytesIO(buf.tobytes()),
            length=len(buf),
            content_type="image/jpeg",
        )
