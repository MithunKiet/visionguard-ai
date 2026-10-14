"""Score independently labeled camera images with the pinned webcam trial model."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

import cv2
import numpy as np

from src.validation.camera import load_manifest, local_file
from src.validation.metrics import read_yolo_labels, score_frame, summarize
from src.validation.ppe_trial import MODEL_PATH, MODEL_SHA256, NAMES, TrialDetector


def evaluate(manifest_path, confidence=0.5, iou_threshold=0.5):
    if not 0 < confidence <= 1 or not 0 < iou_threshold <= 1:
        raise ValueError("Thresholds must be above zero and at most one")
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    if manifest.get("classes") != list(NAMES):
        raise ValueError("Manifest class order must match the six-class trial model")
    root = manifest_path.resolve().parent
    detector = TrialDetector()
    counts = {name: {"tp": 0, "fp": 0, "fn": 0} for name in NAMES}
    by_condition, timings, frames = {}, [], []
    dataset_digest = hashlib.sha256()
    seen_images = set()
    for row in manifest["frames"]:
        image_bytes = local_file(root, row["image"]).read_bytes()
        image_digest = hashlib.sha256(image_bytes).hexdigest()
        if image_digest in seen_images:
            raise ValueError("Duplicate image content would inflate the evaluation")
        seen_images.add(image_digest)
        # imdecode supports Windows Unicode paths, unlike some imread builds.
        frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("A labeled frame cannot be decoded")
        label_path = local_file(root, row["label"])
        truth = read_yolo_labels(label_path, frame.shape[1], frame.shape[0], NAMES)
        label_digest = hashlib.sha256(label_path.read_bytes()).hexdigest()
        dataset_digest.update(bytes.fromhex(image_digest))
        dataset_digest.update(bytes.fromhex(label_digest))
        started = time.perf_counter()
        predictions = detector.detect(frame, confidence)
        timings.append((time.perf_counter() - started) * 1000)
        scored = score_frame(truth, predictions, NAMES, confidence, iou_threshold)
        group = by_condition.setdefault(row["condition"], {name: {"tp": 0, "fp": 0, "fn": 0} for name in NAMES})
        for name, values in scored.items():
            for key, value in values.items():
                counts[name][key] += value
                group[name][key] += value
        frames.append({"frame_index": len(frames), "image_sha256": image_digest, "label_sha256": label_digest,
                       "condition": row["condition"], "classes": scored})
    return {
        "status": "frame_metrics_measured_not_approved", "model_sha256": MODEL_SHA256,
        "model_kind": "six_class_onnx_webcam_trial", "class_order": list(NAMES), "device": "cpu",
        "dataset_id": manifest["dataset_id"],
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "dataset_content_sha256": dataset_digest.hexdigest(),
        "frame_count": len(frames),
        "camera_count": len({row["camera_id"] for row in manifest["frames"]}),
        "session_count": len({(row["camera_id"], row["session_id"]) for row in manifest["frames"]}),
        "confidence_threshold": confidence, "iou_threshold": iou_threshold,
        "classes": summarize(counts), "by_condition": {key: summarize(value) for key, value in by_condition.items()},
        "frames": frames,
        "unobserved_classes": [name for name, values in counts.items() if values["tp"] + values["fn"] == 0],
        "inference_ms_p50": statistics.median(timings),
        "inference_ms_p95": sorted(timings)[math.ceil(0.95 * len(timings)) - 1],
        "held_out_status": "user_declared_not_independently_verified",
        "label_quality_verified": False, "production_approved": False,
        "temporal_alert_pipeline_validated": False, "frames_uploaded": False,
        "operational_alerts_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Choose a new report path; existing evidence is never overwritten")
        if not MODEL_PATH.is_file():
            raise ValueError("Run the trial model download first")
        report = evaluate(args.manifest, args.confidence, args.iou)
        report["created_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(report, file, indent=2, allow_nan=False)
        print("Frame metrics measured. Label quality and production suitability are not verified.")
        for name, values in report["classes"].items():
            precision = f"{values['precision']:.1%}" if values["precision"] is not None else "unmeasured"
            recall = f"{values['recall']:.1%}" if values["recall"] is not None else "unmeasured"
            print(f"{name}: TP={values['tp']} FP={values['fp']} FN={values['fn']} precision={precision} recall={recall}")
    except Exception as error:
        # Do not echo private image paths or native-library diagnostics.
        print(f"Evaluation failed ({type(error).__name__}). Check the model, class order, images, labels and thresholds.", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
