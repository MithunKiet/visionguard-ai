"""Local ONNX webcam trial. No operational events, recording or remote inference."""
import argparse
import ast
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image

MODEL_REVISION = "0d9abf9e606e383e932ecb68723b520b4c4b959d"
MODEL_URL = f"https://raw.githubusercontent.com/M0-AbdElwahab/safety-gear-detector/{MODEL_REVISION}/models/best.onnx"
MODEL_SHA256 = "f7abd19f20a694c6422e7bb9fc647202e0c1cd5c78a3a28f123caeaa87d37098"
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "safety_gear_trial.onnx"
NAMES = ("boots", "helmet", "nohelmet", "novest", "person", "vest")
WINDOW = "VisionGuard PPE trial - Q to finish - no recording"


def verify_model(path):
    with Path(path).open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != MODEL_SHA256:
            raise ValueError("Model checksum mismatch; remove the trial model and download again")


def download_model(path=MODEL_PATH):
    path = Path(path)
    if path.exists():
        verify_model(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".download", delete=False) as target:
            temporary = Path(target.name)
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 50 * 1024 * 1024:
                        raise ValueError("Unexpected model size")
                    target.write(chunk)
        verify_model(temporary)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_frame(frame):
    height, width = frame.shape[:2]
    ratio = min(640 / width, 640 / height)
    size = (round(width * ratio), round(height * ratio))
    offset = ((640 - size[0]) // 2, (640 - size[1]) // 2)
    rgb = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    canvas = Image.new("RGB", (640, 640), (114, 114, 114))
    canvas.paste(rgb.resize(size, Image.Resampling.BILINEAR), offset)
    tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255
    return np.ascontiguousarray(tensor), ratio, offset


def decode_predictions(output, frame_shape, ratio, offset, confidence):
    if output.shape != (1, 10, 8400) or not np.isfinite(output).all():
        raise ValueError("Unsupported or invalid model output")
    candidates = output[0].T
    ids = candidates[:, 4:].argmax(axis=1)
    scores = candidates[:, 4:].max(axis=1)
    result = []
    for class_id, name in enumerate(NAMES):
        selected = np.flatnonzero((ids == class_id) & (scores >= confidence))
        boxes = []
        valid = []
        for index in selected:
            cx, cy, width, height = candidates[index, :4]
            if width > 0 and height > 0:
                boxes.append([float(cx-width/2), float(cy-height/2), float(width), float(height)])
                valid.append(index)
        if not boxes:
            continue
        kept = cv2.dnn.NMSBoxes(boxes, [float(scores[i]) for i in valid], 0.0, 0.7)
        for index in np.asarray(kept).reshape(-1):
            x, y, width, height = boxes[int(index)]
            x1, x2 = np.clip([(x-offset[0])/ratio, (x+width-offset[0])/ratio], 0, frame_shape[1])
            y1, y2 = np.clip([(y-offset[1])/ratio, (y+height-offset[1])/ratio], 0, frame_shape[0])
            if x2 > x1 and y2 > y1:
                result.append({"class_name": name, "confidence": float(scores[valid[int(index)]]),
                               "bbox": [float(x1), float(y1), float(x2), float(y2)]})
    return result


class TrialDetector:
    def __init__(self, path=MODEL_PATH):
        import onnxruntime as ort
        verify_model(path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        names = ast.literal_eval(self.session.get_modelmeta().custom_metadata_map.get("names", "{}"))
        if (len(inputs) != 1 or inputs[0].shape != [1, 3, 640, 640] or inputs[0].type != "tensor(float)"
                or len(outputs) != 1 or outputs[0].shape != [1, 10, 8400] or names != dict(enumerate(NAMES))):
            raise ValueError("Unexpected model contract")
        self.input_name = inputs[0].name

    def detect(self, frame, confidence=0.5):
        tensor, ratio, offset = prepare_frame(frame)
        output = self.session.run(None, {self.input_name: tensor})[0]
        return decode_predictions(output, frame.shape, ratio, offset, confidence)


def trial_worker(config):
    detector = TrialDetector()
    backend = cv2.CAP_ANY
    if sys.platform == "win32":
        backend = cv2.CAP_DSHOW if config["backend"] == "directshow" else cv2.CAP_MSMF
    capture = cv2.VideoCapture(config["camera_index"], backend)
    if not capture.isOpened():
        capture.release()
        return {"status": "camera_unavailable"}
    latest = deque(maxlen=1)
    stop = threading.Event()
    failed = threading.Event()

    def read_camera():
        index = 0
        try:
            while not stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    failed.set()
                    break
                index += 1
                latest.append((index, time.monotonic(), frame))
        except Exception:
            failed.set()
        finally:
            capture.release()

    reader = threading.Thread(target=read_camera, daemon=True)
    reader.start()
    started = time.monotonic()
    last_index = 0
    latencies, dimensions = [], Counter()
    counts = Counter({name: 0 for name in NAMES})
    status = "trial_completed"
    try:
        while time.monotonic() - started < config["seconds"]:
            if failed.is_set() or (latest and time.monotonic() - latest[0][1] > 5):
                status = "camera_read_failed"
                break
            if not latest or latest[0][0] == last_index:
                time.sleep(0.01)
                continue
            last_index, _, frame = latest[0]
            tick = time.perf_counter()
            detections = detector.detect(frame, config["confidence"])
            latencies.append((time.perf_counter() - tick) * 1000)
            dimensions[f"{frame.shape[1]}x{frame.shape[0]}"] += 1
            for detection in detections:
                name = detection["class_name"]
                counts[name] += 1
                x1, y1, x2, y2 = map(int, detection["bbox"])
                color = (0, 100, 255) if name in {"nohelmet", "novest"} else (255, 210, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{name} {detection['confidence']:.2f}", (x1, max(20, y1-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.putText(frame, "PPE TRIAL: predictions only. No boxes does not mean safe.", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.imshow(WINDOW, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                status = "trial_stopped_by_user"
                break
    finally:
        stop.set()
        reader.join(timeout=2)
        cv2.destroyAllWindows()
    return {"status": status if latencies else "no_frames_processed", "processed_frames": len(latencies),
            "elapsed_seconds": time.monotonic() - started, "dimensions": dict(dimensions),
            "detection_box_counts_across_frames": dict(counts),
            "inference_ms_median": statistics.median(latencies) if latencies else None,
            "confidence_threshold": config["confidence"], "model_sha256": MODEL_SHA256,
            "accuracy_validated": False, "production_approved": False, "footage_saved": False,
            "frames_uploaded": False, "operational_alerts_sent": False}


def main():
    if sys.argv[1:] == ["_trial"]:
        print(json.dumps(trial_worker(json.load(sys.stdin)), allow_nan=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download and verify the pinned public trial model only")
    parser.add_argument("--camera-index", type=int, choices=range(33), default=0)
    parser.add_argument("--backend", choices=["directshow", "msmf"], default="directshow")
    parser.add_argument("--seconds", type=int, choices=range(1, 301), default=60)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.download:
            download_model()
            print("Trial model downloaded and SHA-256 verified.")
            return
        if args.output is None or args.output.exists() or not 0 < args.confidence <= 1:
            raise ValueError("Choose a new report path and a confidence threshold above 0 and at most 1")
        verify_model(MODEL_PATH)
        try:
            child = subprocess.run([sys.executable, "-m", "src.validation.ppe_trial", "_trial"],
                                   input=json.dumps({"camera_index": args.camera_index, "backend": args.backend,
                                                     "seconds": args.seconds, "confidence": args.confidence}),
                                   text=True, capture_output=True, timeout=args.seconds + 60,
                                   env={**os.environ, "OPENCV_LOG_LEVEL": "SILENT"})
            report = json.loads(child.stdout) if child.returncode == 0 else {"status": "trial_failed"}
        except subprocess.TimeoutExpired:
            report = {"status": "trial_timeout"}
        report.update(created_at=datetime.now(timezone.utc).isoformat(), source="local_webcam",
                      camera_index=args.camera_index, accuracy_validated=False, production_approved=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as file:
            json.dump(report, file, indent=2, allow_nan=False)
        print(f"PPE trial report written: {report['status']}")
        if report["status"] not in {"trial_completed", "trial_stopped_by_user"}:
            raise SystemExit(2)
    except Exception as error:
        print(f"PPE trial could not complete ({type(error).__name__}). Check dependencies, verified model and camera permissions.", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
