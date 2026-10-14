"""Conservative sizing from an operator-supplied integrated camera pilot report."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

REQUIRED_COMPONENTS = {"camera_decode", "inference", "snapshot_upload", "broker_database",
                       "notifications", "api_review", "live_video"}


def finite(value, minimum=0, maximum=float("inf")):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and minimum <= value <= maximum


def calculate(evidence, target_cameras, headroom=0.3, spare_workers=1, min_hours=24, max_p95_seconds=10):
    if (type(target_cameras) is not int or target_cameras < 1 or not finite(headroom, 0.1, 0.8)
            or type(spare_workers) is not int or spare_workers < 1 or not finite(min_hours, 1)
            or not finite(max_p95_seconds, 0.001)):
        raise ValueError("Invalid sizing policy")
    failures = []
    if evidence.get("scope") != "integrated_camera_pilot":
        failures.append("Integrated camera evidence is required; inference-only throughput cannot size deployment")
    if not evidence.get("hardware_id") or not evidence.get("evidence_reference"):
        failures.append("Identify the measured hardware and source evidence")
    if not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("model_sha256", ""))):
        failures.append("Record the actual deployed model checksum")
    if not finite(evidence.get("observation_hours"), min_hours):
        failures.append("Observation period is shorter than policy or missing")
    components = evidence.get("components_tested")
    if not isinstance(components, list) or not all(name in components for name in REQUIRED_COMPONENTS):
        failures.append("The combined inference, delivery, API and video workload must be tested")
    if evidence.get("failover_drill_passed") is not True:
        failures.append("A worker-failure/reassignment drill is required")
    for key in ("lost_events", "failed_notifications", "stale_frame_events"):
        if not finite(evidence.get(key), 0, 0):
            failures.append(f"{key} must be measured and zero")
    for key in ("peak_cpu_fraction", "peak_ram_fraction", "peak_gpu_memory_fraction"):
        if not finite(evidence.get(key), 0, 0.85):
            failures.append(f"{key} must be measured and at most 0.85")
    cameras = evidence.get("cameras")
    if not isinstance(cameras, list) or not cameras:
        failures.append("Per-camera measurements are missing")
        cameras = []
    ids = set()
    for row in cameras:
        if not isinstance(row, dict):
            failures.append("Invalid camera measurement")
            continue
        camera_id = row.get("camera_id")
        if not isinstance(camera_id, str) or not camera_id or camera_id in ids:
            failures.append("Camera identifiers must be nonempty and unique")
        else:
            ids.add(camera_id)
        target = row.get("target_fps")
        if not finite(target, 0.01, 60) or not finite(row.get("processed_fps"), 0) or row["processed_fps"] < target * 0.95:
            failures.append("Every camera must sustain at least 95% of its configured inference FPS")
        if not finite(row.get("capture_to_alert_p95_seconds"), 0, max_p95_seconds):
            failures.append("Capture-to-alert latency is missing or exceeds policy")
        if not finite(row.get("inference_errors"), 0, 0):
            failures.append("Every camera must have zero measured inference errors")
    usable = math.floor(len(cameras) * (1 - headroom))
    if usable < 1:
        failures.append("Measured camera count leaves no capacity after headroom")
    result = {"status": "insufficient_evidence" if failures else "candidate_plan",
              "production_approved": False, "evidence_independently_verified": False,
              "blocking_reasons": sorted(set(failures)), "target_cameras": target_cameras,
              "headroom_fraction": headroom, "spare_workers": spare_workers,
              "minimum_observation_hours": min_hours, "maximum_capture_to_alert_p95_seconds": max_p95_seconds,
              "capacity_basis": "identical hardware, model, camera profiles and combined workload"}
    if not failures:
        active = math.ceil(target_cameras / usable)
        result.update(measured_cameras_per_worker=len(cameras), planned_cameras_per_worker=usable,
                      active_workers=active, total_workers=active + spare_workers,
                      remaining_capacity_after_reserved_worker_failures=active * usable)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--target-cameras", type=int, required=True)
    parser.add_argument("--headroom", type=float, default=0.3)
    parser.add_argument("--spare-workers", type=int, default=1)
    parser.add_argument("--min-hours", type=float, default=24)
    parser.add_argument("--max-p95-seconds", type=float, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path; existing evidence is never overwritten")
    try:
        content = args.evidence.read_bytes()
        report = calculate(json.loads(content), args.target_cameras, args.headroom, args.spare_workers, args.min_hours, args.max_p95_seconds)
    except (ValueError, TypeError, AttributeError, OSError):
        parser.error("Invalid evidence or sizing policy")
    report.update(evidence_sha256=hashlib.sha256(content).hexdigest(), created_at=datetime.now(timezone.utc).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(report["status"])
    if report["blocking_reasons"]:
        for reason in report["blocking_reasons"]:
            print(f"- {reason}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
