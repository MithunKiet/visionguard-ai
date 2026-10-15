"""Bounded local model/device startup smoke; never opens cameras or sends alerts."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys


def probe(config):
    from src.config.settings import settings
    settings.YOLO_MODEL_PATH = config["weights"]
    settings.YOLO_MODEL_SHA256 = config["model_sha256"]
    settings.USE_GPU = config["device"] == "cuda"
    settings.ENVIRONMENT = "production" if settings.USE_GPU else "validation"
    settings.DEMO_MODE = False
    settings.ROBOFLOW_API_KEY = ""
    from src.pipeline.detector import PPEDetector, PPE_CLASSES
    model = PPEDetector()
    fields = model.heartbeat_fields()
    import torch
    return {"status": "model_ready", "scope": "startup_smoke", "production_approved": False,
        "actual_device": model.device, "gpu_available": fields["gpu_available"],
        "gpu_name": torch.cuda.get_device_name(0) if fields["gpu_available"] else None,
        "model_version": fields["model_version"], "model_sha256": model.model_sha256,
        "classes": list(PPE_CLASSES.values()), "warmup_shape": [640, 640, 3],
        "packages": {name: importlib.metadata.version(name) for name in ("torch", "ultralytics", "numpy")}}


def main():
    if sys.argv[1:] == ["_run"]:
        config = json.load(sys.stdin)
        try:
            with redirect_stdout(sys.stderr):
                report = probe(config)
        except Exception as error:
            report = {"status": "model_readiness_failed", "production_approved": False, "error_type": type(error).__name__}
        print(json.dumps(report, allow_nan=False))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--device", required=True, choices=["cpu", "cuda"])
    parser.add_argument("--timeout-seconds", type=int, choices=range(10, 601), default=120)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or not args.weights.is_file() or not re.fullmatch(r"[a-fA-F0-9]{64}", args.model_sha256):
        parser.error("Provide local trusted weights, their expected SHA-256 and a new output path")
    config = {"weights": str(args.weights.resolve()), "model_sha256": args.model_sha256, "device": args.device}
    try:
        result = subprocess.run([sys.executable, "-m", "src.validation.model_readiness", "_run"],
            input=json.dumps(config), text=True, capture_output=True, timeout=args.timeout_seconds)
        report = json.loads(result.stdout) if result.returncode == 0 else {"status": "model_readiness_failed", "production_approved": False}
    except subprocess.TimeoutExpired:
        report = {"status": "model_readiness_timeout", "production_approved": False}
    except (ValueError, OSError):
        report = {"status": "model_readiness_failed", "production_approved": False}
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(report["status"])
    if report["status"] != "model_ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
