import asyncio
import time
from contextlib import aclosing
from datetime import datetime, timezone
import structlog
import numpy as np

from src.pipeline.frame_reader import FrameReader
from src.pipeline.batch_detector import BatchDetector, DetectionExpired
from src.pipeline.ppe_validator import PPEValidator
from src.events.publisher import publish, publish_incident
from src.config.settings import settings
from src.config.ownership import event_ownership, lease_valid, lease_clock
from src.health.metrics import (
    camera_last_processed_timestamp, camera_target_fps, frames_processed_total, violations_detected_total,
    frame_local_age, frames_discarded, camera_lease_remaining, camera_lease_expirations,
)

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

class CameraWorker:

    def __init__(self, camera_id: str, rtsp_url: str, zone_config: dict,
                 enterprise_id: str, factory_id: str, zone_id: str, detector: BatchDetector,
                 active: bool = True, ppe_overrides: dict | None = None, lease: dict | None = None):
        self.lease = lease
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.ppe_overrides = ppe_overrides or {}
        self.zone_config = self._normalize_config(zone_config or {})
        self.enterprise_id = enterprise_id
        self.factory_id = factory_id
        self.zone_id = zone_id
        # Manual on/off toggle (hot-applied via config_events, see zone_sync.py).
        # The RTSP connection stays open and frames keep being read even when
        # off, so turning back on is instant — no reconnect needed.
        self._active = active
        self._policy_revision = 0
        camera_target_fps.labels(camera_id=self.camera_id).set(self.zone_config.get("frame_sample_fps", 2) if active else 0)

        camera_last_processed_timestamp.labels(camera_id=self.camera_id).set(0)
        frames_processed_total.labels(camera_id=self.camera_id).inc(0)
        self._reader = FrameReader(camera_id, rtsp_url, self.zone_config.get("frame_sample_fps", 2), on_status=self._on_stream_status)
        if lease is not None:
            self._reader.set_lease_deadline(lease["deadline"])
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

    def update_lease(self, lease):
        if self.lease is None or lease["token"] != self.lease["token"]:
            raise ValueError("A new ownership generation requires a fresh camera pipeline")
        self.lease = lease
        self._reader.set_lease_deadline(lease["deadline"])

    async def _publish(self, route, body):
        ownership = event_ownership(self.lease) if self.lease is not None else {}
        await publish(route, {**body, **ownership})

    async def _publish_incident(self, route, body, frame):
        ownership = event_ownership(self.lease) if self.lease is not None else {}
        await publish_incident(route, {**body, **ownership}, frame)

    async def run(self):
        # Independent of assignment polling, HTTP timeouts and GPU inference.
        task = asyncio.create_task(self._run())
        try:
            while not task.done():
                if self.lease is not None:
                    camera_lease_remaining.labels(camera_id=self.camera_id).set(max(0, self.lease["deadline"] - lease_clock()))
                if self.lease is not None and not lease_valid(self.lease):
                    self._active = False
                    self._validator.mark_gap()
                    camera_target_fps.labels(camera_id=self.camera_id).set(0)
                    camera_lease_expirations.labels(camera_id=self.camera_id).inc()
                    log.warning("camera_worker.lease_expired", camera_id=self.camera_id)
                    return
                await asyncio.sleep(0.1)
            await task
        finally:
            camera_lease_remaining.labels(camera_id=self.camera_id).set(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _on_stream_status(self, offline: bool) -> None:
        self._validator.mark_gap()
        self._policy_revision += 1
        self._last_spec_check = 0
        event = "camera_offline_detected" if offline else "camera_reconnected"
        await self._publish(f"events.{event}", {"event": event, "camera_id": self.camera_id,
            "enterprise_id": self.enterprise_id, "factory_id": self.factory_id, "zone_id": self.zone_id})

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._policy_revision += 1
        self._validator.mark_gap()
        camera_target_fps.labels(camera_id=self.camera_id).set(self.zone_config.get("frame_sample_fps", 2) if active else 0)
        log.info("camera_worker.active_changed", camera_id=self.camera_id, active=active)

    def _normalize_config(self, config: dict) -> dict:
        result = dict(config)
        required = set(config.get("required_ppe_types", config.get("ppe_required", ["helmet", "vest"])))
        result["ppe_required"] = sorted((required - {k for k, v in self.ppe_overrides.items() if v is False}) |
                                       {k for k, v in self.ppe_overrides.items() if v is True})
        result["version"] = config.get("version", config.get("config_version", 1))
        return result

    def apply_zone_config(self, new_config: dict) -> None:
        """Hot-swap zone config (rule #8) — takes effect on the next frame.
        Frame sampling rate is pushed down into the reader immediately."""
        self.zone_config = self._normalize_config(new_config)
        self._policy_revision += 1
        self._validator = PPEValidator()
        fps = new_config.get("frame_sample_fps")
        if fps:
            self._reader.set_sample_fps(fps)
        camera_target_fps.labels(camera_id=self.camera_id).set(self._reader.sample_fps if self._active else 0)

    async def _run(self) -> None:
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
                async with aclosing(self._reader.read_frames()) as frames:
                    async for packet in frames:
                        await self._process_frame(packet.image, packet=packet)
                        self._failure_count = 0
            except Exception as e:
                self._failure_count += 1
                log.error("camera_worker.error", camera_id=self.camera_id, error_type=type(e).__name__,
                          failures=self._failure_count)

                if self._failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                    self._isolated = True
                    await self._publish("events.camera_offline_detected", {
                        "event": "camera_offline_detected",
                        "camera_id": self.camera_id,
                        "enterprise_id": self.enterprise_id,
                        "factory_id": self.factory_id,
                        "zone_id": self.zone_id,
                        "reason": "circuit_breaker_triggered",
                    })
                    log.error("camera_worker.circuit_breaker_open", camera_id=self.camera_id)
                    await asyncio.sleep(60)
                    self._isolated = False
                    self._failure_count = 0

                await asyncio.sleep(5)

    async def _process_frame(self, frame: np.ndarray, *, packet=None) -> None:
        if not self._active:
            # Turned off — drop the frame with zero GPU/CPU work. The RTSP
            # read loop above keeps running so the stream stays connected
            # and turning back on is instant.
            return

        received_at = packet.received_at if packet else time.monotonic()
        wall_time = packet.received_wall_time if packet else time.time()
        revision = self._policy_revision
        validator = self._validator

        def discard_if_invalid(phase):
            reason = None
            age = time.monotonic() - received_at
            if self.lease is not None and not lease_valid(self.lease):
                reason = "lease_expired"
            elif not 0 <= age <= settings.FRAME_MAX_AGE_SECONDS:
                reason = f"stale_{phase}"
            elif not self._active or revision != self._policy_revision:
                reason = "policy_changed"
            elif packet and not self._reader.is_current(packet):
                reason = "stream_changed"
            if reason:
                validator.mark_gap()
                frames_discarded.labels(camera_id=self.camera_id, reason=reason).inc()
            return reason is not None

        if discard_if_invalid("before_inference"):
            return

        # Submits to the shared BatchDetector, which groups this frame with
        # whatever other cameras submit within the same short window and
        # runs one batched GPU inference call for all of them — cheaper per
        # camera than each running its own single-image call, and never
        # blocks this worker's event loop (inference itself runs in a
        # thread inside BatchDetector).
        await self._check_camera_spec()

        if discard_if_invalid("before_inference"):
            return

        try:
            detections = await self._detector.detect(frame, camera_id=self.camera_id,
                deadline=received_at + settings.FRAME_MAX_AGE_SECONDS)
        except DetectionExpired:
            validator.mark_gap()
            frames_discarded.labels(camera_id=self.camera_id, reason="stale_inference").inc()
            return
        except Exception:
            validator.mark_gap()
            raise
        frame_local_age.labels(camera_id=self.camera_id).observe(max(0, time.monotonic() - received_at))
        if discard_if_invalid("after_inference"):
            return
        frames_processed_total.labels(camera_id=self.camera_id).inc()
        camera_last_processed_timestamp.labels(camera_id=self.camera_id).set(time.time())
        violations = validator.evaluate(detections, self.zone_config, auto_mark=False)
        observed_at = datetime.fromtimestamp(wall_time, timezone.utc).isoformat()

        for v in violations:
            if discard_if_invalid("before_event"):
                return
            if v.get("review"):
                await self._publish("events.low_confidence_violation", {
                    "event": "low_confidence_violation",
                    "camera_id": self.camera_id,
                    "enterprise_id": self.enterprise_id,
                    "factory_id": self.factory_id,
                    "zone_id": self.zone_id,
                    **{k: value for k, value in v.items() if k != "tracker_key"},
                    "timestamp": observed_at,
                })
            else:
                await self._publish_incident(f"events.{v['event']}", {
                    "event": v["event"],
                    "camera_id": self.camera_id,
                    "enterprise_id": self.enterprise_id,
                    "factory_id": self.factory_id,
                    "zone_id": self.zone_id,
                    "confidence": v["confidence"],
                    "track_id": v.get("track_id"),
                    "bbox": v["bbox"],
                    "config_version": self.zone_config.get("version", 1),
                    "timestamp": observed_at,
                }, frame)

            validator.acknowledge(v)
            violations_detected_total.labels(camera_id=self.camera_id, violation_type=v["event"]).inc()

        if not discard_if_invalid("before_event"):
            await self._publish_occupancy(detections, timestamp=observed_at)

    async def _publish_occupancy(self, detections: list, *, timestamp=None) -> None:
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
            await self._publish("events.occupancy_updated", {
                "event": "occupancy_updated",
                "camera_id": self.camera_id,
                "enterprise_id": self.enterprise_id,
                "factory_id": self.factory_id,
                "zone_id": self.zone_id,
                "count": count,
                **({"timestamp": timestamp} if timestamp else {}),
            })

        max_occupancy = self.zone_config.get("max_occupancy")
        if (
            max_occupancy
            and count > max_occupancy
            and (now - self._last_overcrowding_fired) >= OVERCROWDING_COOLDOWN_SECONDS
        ):
            await self._publish("events.overcrowding_detected", {
                "event": "overcrowding_detected",
                "camera_id": self.camera_id,
                "enterprise_id": self.enterprise_id,
                "factory_id": self.factory_id,
                "zone_id": self.zone_id,
                "count": count,
                "max_occupancy": max_occupancy,
                **({"timestamp": timestamp} if timestamp else {}),
            })
            self._last_overcrowding_fired = now
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
        await self._publish("events.camera_spec_mismatch", {
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
