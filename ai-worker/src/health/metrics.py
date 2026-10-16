"""Worker throughput, request latency and health metrics.

The bounded queue alone cannot prove capacity: each camera waits for its own
result, so overload also appears as falling per-camera FPS and stale results.
Inference timings exclude camera/network buffering and alert delivery.
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
    "Frames currently waiting in the shared BatchDetector queue",
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
    "Fresh inference results accepted by the camera pipeline",
    ["camera_id"],
)

violations_detected_total = Counter(
    "vg_violations_detected_total",
    "Total violations accepted by durable local storage",
    ["camera_id", "violation_type"],
)


def start_metrics_server(port: int) -> None:
    from src.config.settings import settings
    worker_identity.labels(reported_worker_id=settings.WORKER_ID,
        reported_enterprise_id=settings.ENTERPRISE_ID).set(1)
    start_http_server(port)
    log.info("metrics.started", port=port)

# These signals measure inference service behavior, not camera capture latency.
detection_failures_total = Counter(
    "vg_detection_failures_total", "Detection requests rejected or failed", ["camera_id", "reason"],
)
inference_batch_seconds = Histogram(
    "vg_inference_batch_seconds", "Wall time for one batched model call including preprocessing/postprocessing",
)
camera_target_fps = Gauge(
    "vg_camera_target_fps", "Configured sampled detection FPS; zero when unassigned or inactive", ["camera_id"],
)
camera_last_processed_timestamp = Gauge(
    "vg_camera_last_processed_timestamp_seconds", "Unix time of the last successful inference result", ["camera_id"],
)

edge_pending = Gauge("vg_edge_pending", "Durable edge records awaiting delivery", ["channel"])
edge_pending_bytes = Gauge("vg_edge_pending_bytes", "Logical bytes retained by the edge journal")
edge_oldest_age = Gauge("vg_edge_oldest_age_seconds", "Age of oldest retained edge record")
edge_rejected = Counter("vg_edge_rejected_total", "Events not accepted by durable local storage")
edge_delivery_failures = Counter("vg_edge_delivery_failures_total", "Edge delivery retry failures", ["channel"])
edge_cache_active = Gauge("vg_edge_assignment_cache_active", "1 while relying on cached assignments")

capture_last_received = Gauge("vg_capture_last_received_timestamp_seconds", "Wall time after the latest sampled frame decoded locally", ["camera_id"])
capture_restarts = Counter("vg_capture_restarts_total", "Capture process restarts", ["camera_id", "reason"])
frames_discarded = Counter("vg_frames_discarded_total", "Frames/results discarded before violation acceptance", ["camera_id", "reason"])
frame_local_age = Histogram("vg_frame_local_age_seconds", "Age since local decode at inference result; excludes upstream buffering", ["camera_id"])
model_ready = Gauge("vg_model_ready", "Verified model startup and no observed runtime readiness failure")
model_cuda_active = Gauge("vg_model_cuda_active", "1 when the ready model and predictor use CUDA")

camera_lease_remaining = Gauge("vg_camera_lease_remaining_seconds", "Remaining local camera authorization, including stop margin", ["camera_id"])
camera_lease_expirations = Counter("vg_camera_lease_expirations_total", "Camera pipelines stopped because ownership expired", ["camera_id"])

worker_identity = Gauge("vg_worker_identity_info", "Runtime identity independent of scrape configuration", ["reported_worker_id", "reported_enterprise_id"])
