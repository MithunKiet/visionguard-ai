"""Inference-only load sweep. Never opens cameras or publishes operational events."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from src.pipeline.batch_detector import BatchDetector


def percentile(values, fraction):
    return sorted(values)[math.ceil(fraction * len(values)) - 1] if values else None


async def measure(detector, frames, cameras, fps, seconds, p95_limit_ms, min_fps_ratio):
    started = time.monotonic()
    deadline = started + seconds

    async def camera(index):
        latencies, failures, missed, completed_after_window = [], 0, 0, 0
        slot = 0
        while started + slot / fps < deadline:
            due = started + slot / fps
            now = time.monotonic()
            if now >= deadline:
                missed += max(0, math.ceil(seconds * fps) - slot)
                break
            if now > due + 1 / fps:
                skipped = int((now - due) * fps)
                missed += skipped
                slot += skipped
                continue
            await asyncio.sleep(max(0, due - now))
            tick = time.monotonic()
            try:
                await detector.detect(frames[(index + slot) % len(frames)], camera_id=f"benchmark-{index}")
                if time.monotonic() <= deadline:
                    latencies.append((time.monotonic() - tick) * 1000)
                else:
                    completed_after_window += 1
            except Exception:
                failures += 1
            slot += 1
        return {"camera_index": index, "completed_frames": len(latencies), "achieved_fps": len(latencies) / seconds,
                "failures": failures, "missed_schedule_slots": missed, "completed_after_window": completed_after_window,
                "p95_ms": percentile(latencies, 0.95)}

    rows = await asyncio.gather(*(camera(index) for index in range(cameras)))
    passed = all(row["failures"] == 0 and row["achieved_fps"] >= fps * min_fps_ratio
                 and row["p95_ms"] is not None and row["p95_ms"] <= p95_limit_ms for row in rows)
    return {"camera_equivalents": cameras, "window_seconds": seconds, "requested_fps_per_camera": fps,
            "total_achieved_fps": sum(row["achieved_fps"] for row in rows), "per_camera": rows,
            "inference_targets_met": passed}


def load_images(manifest_path):
    import cv2
    import numpy as np
    root = manifest_path.resolve().parent
    manifest = json.loads(manifest_path.read_text())
    names = manifest.get("images")
    if not isinstance(names, list) or not 1 <= len(names) <= 16:
        raise ValueError("List between 1 and 16 representative images")
    frames, hashes = [], []
    for name in names:
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root):
            raise ValueError("Images must be inside the manifest directory")
        content = path.read_bytes()
        frame = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0] * frame.shape[1] > 4096 * 4096:
            raise ValueError("Image is invalid or exceeds the benchmark size limit")
        frames.append(frame)
        hashes.append({"sha256": hashlib.sha256(content).hexdigest(), "width": frame.shape[1], "height": frame.shape[0]})
    return frames, hashes


async def run(config):
    # Set the actual production detector's settings before importing it.
    from src.config.settings import settings
    weights = Path(config["weights"])
    with weights.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != config["model_sha256"]:
        raise ValueError("Model checksum differs from the expected trusted artifact")
    settings.YOLO_MODEL_PATH = str(weights.resolve())
    settings.YOLO_MODEL_SHA256 = digest
    settings.ENVIRONMENT = "validation"  # Explicit CPU comparisons are not production deployment.
    settings.DEMO_MODE = False
    settings.ROBOFLOW_API_KEY = ""
    settings.USE_GPU = config["device"] == "cuda"
    import torch
    if settings.USE_GPU and not torch.cuda.is_available():
        raise ValueError("Requested CUDA hardware is unavailable")
    frames, image_hashes = load_images(Path(config["manifest"]))
    from src.pipeline.detector import PPEDetector
    model = PPEDetector()
    detector = BatchDetector(model)
    levels = []
    try:
        for _ in range(3):
            await detector.detect(frames[0], "benchmark-warmup")
        for cameras in config["cameras"]:
            if settings.USE_GPU:
                torch.cuda.reset_peak_memory_stats()
            level = await measure(detector, frames, cameras, config["fps"], config["seconds"], config["p95_ms"], config["min_fps_ratio"])
            level["gpu_peak_allocated_bytes"] = torch.cuda.max_memory_allocated() if settings.USE_GPU else None
            levels.append(level)
    finally:
        await detector.stop()
    passing = [level["camera_equivalents"] for level in levels if level["inference_targets_met"]]
    return {
        "status": "inference_benchmark_completed", "scope": "inference_only", "production_approved": False,
        "actual_device": str(model._model.device),
        "gpu_name": torch.cuda.get_device_name() if settings.USE_GPU else None,
        "cpu_architecture": platform.machine(), "logical_cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
        "packages": {name: importlib.metadata.version(name) for name in ["torch", "ultralytics", "numpy"]},
        "model_sha256": digest, "images": image_hashes,
        "queue_size": settings.DETECTION_QUEUE_SIZE, "request_timeout_seconds": settings.DETECTION_TIMEOUT_SECONDS,
        "p95_limit_ms": config["p95_ms"], "min_fps_ratio": config["min_fps_ratio"], "levels": levels,
        "highest_tested_passing_camera_equivalents": max(passing, default=0),
        "excluded": ["camera_decode", "capture_freshness", "tracking_and_voting", "snapshot_upload",
                     "broker", "database", "notifications", "live_video", "accuracy"],
    }


def main():
    if sys.argv[1:] == ["_run"]:
        # Model libraries can print progress to stdout: reserve stdout for JSON.
        from contextlib import redirect_stdout
        config = json.load(sys.stdin)
        with redirect_stdout(sys.stderr):
            report = asyncio.run(run(config))
        print(json.dumps(report, allow_nan=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--cameras", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--fps", type=int, choices=range(1, 31), default=2)
    parser.add_argument("--seconds", type=int, choices=range(10, 1801), default=60)
    parser.add_argument("--p95-ms", type=float, default=500)
    parser.add_argument("--min-fps-ratio", type=float, default=0.95)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists() or not args.weights.is_file() or not args.manifest.is_file():
            raise ValueError("Provide local weights, a manifest and a new report path")
        if (not 0 < args.p95_ms < 120000 or not 0 < args.min_fps_ratio <= 1
                or not 1 <= len(args.cameras) <= 10 or any(not 1 <= n <= 128 for n in args.cameras)):
            raise ValueError("Invalid benchmark limits")
        config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items() if key != "output"}
        config["cameras"] = sorted(set(args.cameras))
        from src.config.settings import settings
        try:
            result = subprocess.run([sys.executable, "-m", "src.capacity.benchmark", "_run"], input=json.dumps(config),
                text=True, capture_output=True, timeout=len(config["cameras"]) * (args.seconds + settings.DETECTION_TIMEOUT_SECONDS) + 120)
            report = json.loads(result.stdout) if result.returncode == 0 else {"status": "benchmark_failed", "production_approved": False}
        except subprocess.TimeoutExpired:
            report = {"status": "benchmark_timeout", "production_approved": False}
        report["created_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as file:
            json.dump(report, file, indent=2, allow_nan=False)
        print(report["status"])
        if report["status"] != "inference_benchmark_completed":
            raise SystemExit(2)
    except Exception as error:
        print(f"Benchmark could not complete ({type(error).__name__}); verify inputs and inference dependencies.", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
