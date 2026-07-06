"""
Prometheus metrics for capacity planning — answers "how many cameras can
one worker/GPU handle" from real numbers instead of guessing:

- vg_detection_queue_depth: frames waiting on the GPU right now. Sustained
  growth means cameras are submitting faster than the GPU can drain —
  the clearest "you're over capacity" signal.
- vg_frame_processing_seconds: submit-to-result latency per camera. Rising
  latency under load is the leading indicator, before the queue visibly backs up.
- vg_batch_size: how many frames land in each GPU call (max 8, see
  batch_detector.py). Consistently near 1 means load is too low to batch
  effectively; near 8 means the GPU is well-utilized.
- vg_camera_connected / vg_frame_reader_reconnect_total: stream health,
  independent of processing load.
- vg_frames_processed_total / vg_violations_detected_total: throughput.

Exposed on METRICS_PORT (default 8001) via prometheus_client's own tiny
HTTP server — started once at worker startup, no FastAPI/aiohttp needed.
"""
import structlog
from prometheus_client import Counter, Gauge, Histogram, start_http_server

log = structlog.get_logger()

frame_processing_seconds = Histogram(
    "vg_frame_processing_seconds",
    "Time from a frame being submitted for detection to its result being returned",
    ["camera_id"],
)

batch_size = Histogram(
    "vg_batch_size",
    "Number of frames grouped into a single GPU inference call",
    buckets=(1, 2, 3, 4, 5, 6, 7, 8),
)

detection_queue_depth = Gauge(
    "vg_detection_queue_depth",
    "Frames waiting in the shared BatchDetector queue, sampled per batch cycle",
)

camera_connected = Gauge(
    "vg_camera_connected",
    "1 if the camera's RTSP stream is currently connected, else 0",
    ["camera_id"],
)

frame_reader_reconnects_total = Counter(
    "vg_frame_reader_reconnects_total",
    "Total RTSP reconnect attempts",
    ["camera_id"],
)

frames_processed_total = Counter(
    "vg_frames_processed_total",
    "Total frames run through detection",
    ["camera_id"],
)

violations_detected_total = Counter(
    "vg_violations_detected_total",
    "Total violations published",
    ["camera_id", "violation_type"],
)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    log.info("metrics.started", port=port)
