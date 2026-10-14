"""Run with python -m src.validation.camera; never publishes operational events."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from urllib.parse import urlsplit

from src.validation.metrics import read_yolo_labels, score_frame, summarize


def probe_worker(config):
    # Parent discards stderr, including native FFmpeg diagnostics that can
    # contain RTSP passwords. The URL travels through stdin, never argv/logs.
    import cv2
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    cap = cv2.VideoCapture(config["url"], cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000])
    try:
        if not cap.isOpened():
            return {"status": "unreachable", "frames_decoded": 0}
        reported_fps = cap.get(cv2.CAP_PROP_FPS)
        start = time.monotonic()
        first_frame_at = None
        last_frame_at = None
        gaps, luminance = [], []
        dimensions = Counter()
        read_failed = False
        while time.monotonic() - start < config["seconds"]:
            ok, frame = cap.read()
            now = time.monotonic()
            if not ok:
                read_failed = True
                break
            dimensions[f"{frame.shape[1]}x{frame.shape[0]}"] += 1
            if first_frame_at is None:
                first_frame_at = now
            if last_frame_at is not None:
                gaps.append(now - last_frame_at)
            last_frame_at = now
            luminance.append(float(cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY).mean()))
        elapsed = time.monotonic() - start
        frames = sum(dimensions.values())
        return {"status": "stream_measured" if frames > 1 and not read_failed else "stream_incomplete",
                "frames_decoded": frames, "read_failed": read_failed, "elapsed_seconds": elapsed,
                "reported_fps": reported_fps if math.isfinite(reported_fps) and reported_fps > 0 else None,
                "decoded_fps": (frames - 1) / (last_frame_at - first_frame_at) if frames > 1 and last_frame_at > first_frame_at else None,
                "dimensions": dict(dimensions), "max_interframe_gap_seconds": max(gaps, default=None),
                "mean_luminance_0_255": statistics.mean(luminance) if luminance else None,
                "accuracy_validated": False, "footage_saved": False}
    finally:
        cap.release()


def probe(env_name, seconds):
    if not 1 <= seconds <= 300:
        raise ValueError("Probe duration must be between 1 and 300 seconds")
    url = os.environ.get(env_name, "")
    parsed = urlsplit(url)
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname or parsed.fragment:
        raise ValueError("Set the named environment variable to the authorized RTSP URL")
    try:
        child = subprocess.run([sys.executable, "-m", "src.validation.camera", "_probe"],
                               input=json.dumps({"url": url, "seconds": seconds}), text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=seconds + 25,
                               env={**os.environ, "OPENCV_LOG_LEVEL": "SILENT"})
        if child.returncode:
            return {"status": "probe_failed", "accuracy_validated": False}
        return json.loads(child.stdout)
    except subprocess.TimeoutExpired:
        return {"status": "probe_timeout", "accuracy_validated": False}


def local_file(root, relative):
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Manifest files must exist inside the dataset directory")
    return path


def load_manifest(path):
    data = json.loads(path.read_text())
    if data.get("split") != "held_out" or data.get("source") != "real_camera" or not data.get("dataset_id"):
        raise ValueError("Declare a real-camera held-out dataset with its own ID")
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("The manifest must list labeled frames")
    root = path.resolve().parent
    seen_images, seen_labels = set(), set()
    for row in frames:
        if not all(isinstance(row.get(key), str) and row[key].strip() for key in
                   ("image", "label", "camera_id", "session_id", "condition")):
            raise ValueError("Each frame requires image, label, camera, session and condition")
        image, label = local_file(root, row["image"]), local_file(root, row["label"])
        if image in seen_images or label in seen_labels:
            raise ValueError("Duplicate frames or reused label files would inflate the evaluation")
        seen_images.add(image)
        seen_labels.add(label)
    return data


def evaluate(manifest_path, weights, confidence, iou_threshold, device):
    manifest = load_manifest(manifest_path)
    if not weights.is_file():
        raise ValueError("Supply the local PPE checkpoint; synthetic and remote fallback are disabled")
    import cv2
    from src.config.settings import settings
    # Same preprocessing and detector class mapping as production; no network
    # inference, demo detections, database writes, notifications or model deploy.
    settings.YOLO_MODEL_PATH = str(weights.resolve())
    settings.DEMO_MODE = False
    settings.ROBOFLOW_API_KEY = ""
    settings.USE_GPU = device == "cuda"
    from src.pipeline.detector import PPEDetector, PPE_CLASSES
    detector = PPEDetector()
    classes = list(PPE_CLASSES.values())
    counts = {name: {"tp": 0, "fp": 0, "fn": 0} for name in classes}
    by_condition, timings = {}, []
    dataset_digest = hashlib.sha256()
    root = manifest_path.resolve().parent
    for row in manifest["frames"]:
        image_path = local_file(root, row["image"])
        label_path = local_file(root, row["label"])
        for path in (image_path, label_path):
            with path.open("rb") as file:
                dataset_digest.update(hashlib.file_digest(file, "sha256").digest())
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise ValueError("A labeled frame cannot be decoded")
        height, width = frame.shape[:2]
        truth = read_yolo_labels(label_path, width, height, classes)
        started = time.perf_counter()
        predictions = [{"class_name": d.class_name, "confidence": d.confidence, "bbox": list(d.bbox)}
                       for d in detector.detect(frame)]
        timings.append((time.perf_counter() - started) * 1000)
        scored = score_frame(truth, predictions, classes, confidence, iou_threshold)
        group = by_condition.setdefault(row["condition"], {name: {"tp": 0, "fp": 0, "fn": 0} for name in classes})
        for name, values in scored.items():
            for key, value in values.items():
                counts[name][key] += value
                group[name][key] += value
    with weights.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    return {"status": "frame_metrics_measured_not_approved", "dataset_id": manifest["dataset_id"],
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "model_sha256": digest,
            "dataset_content_sha256": dataset_digest.hexdigest(),
            "device": str(detector._model.device), "frame_count": len(timings),
            "camera_count": len({r["camera_id"] for r in manifest["frames"]}),
            "session_count": len({(r["camera_id"], r["session_id"]) for r in manifest["frames"]}),
            "confidence_threshold": confidence, "iou_threshold": iou_threshold,
            "classes": summarize(counts), "by_condition": {key: summarize(value) for key, value in by_condition.items()},
            "unobserved_classes": [key for key, value in counts.items() if value["tp"] + value["fn"] == 0],
            "inference_ms_p50": statistics.median(timings), "inference_ms_p95": sorted(timings)[math.ceil(0.95*len(timings))-1],
            "temporal_alert_pipeline_validated": False, "production_approved": False}


def main():
    if sys.argv[1:] == ["_probe"]:
        print(json.dumps(probe_worker(json.load(sys.stdin)), allow_nan=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("probe", help="Decode an authorized RTSP stream without recording")
    p.add_argument("--url-env", default="VALIDATION_RTSP_URL")
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("evaluate", help="Score independently labeled held-out camera frames")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--confidence", type=float, default=0.6)
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Choose a new report path; existing evidence is never overwritten")
        if args.mode == "probe":
            report = probe(args.url_env, args.seconds)
        else:
            if not 0 <= args.confidence <= 1 or not 0 < args.iou <= 1:
                raise ValueError("Invalid scoring threshold")
            report = evaluate(args.manifest, args.weights, args.confidence, args.iou, args.device)
        report["created_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as file:
            json.dump(report, file, indent=2, allow_nan=False)
        print(f"Validation report written: {report['status']}")
        if report["status"] not in {"stream_measured", "frame_metrics_measured_not_approved"}:
            raise SystemExit(2)
    except Exception as error:
        # Never echo camera URLs, provider responses or private dataset paths.
        print(f"Validation could not complete ({type(error).__name__}); check inputs and installed dependencies", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
