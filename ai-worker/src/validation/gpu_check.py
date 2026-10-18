"""Bounded local CUDA computation check; no checkpoints, cameras or network calls."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


def probe():
    import torch

    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        return {"status": "gpu_check_failed", "reason": "cuda_unavailable",
                "torch_version": torch.__version__, "torch_cuda_version": torch.version.cuda}
    device = "cuda:0"
    props = torch.cuda.get_device_properties(0)
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    torch.cuda.reset_peak_memory_stats(0)
    with torch.inference_mode():
        left = torch.ones((1024, 1024), dtype=torch.float32, device=device)
        right = torch.ones_like(left)
        expected = torch.full_like(left, 1024)
        for _ in range(3):
            result = left @ right
        torch.cuda.synchronize(0)
        timings = []
        for _ in range(10):
            started = time.perf_counter()
            result = left @ right
            torch.cuda.synchronize(0)
            timings.append((time.perf_counter() - started) * 1000)
        if str(result.device) != device or not torch.allclose(result, expected):
            return {"status": "gpu_check_failed", "reason": "incorrect_cuda_result"}
    return {"status": "cuda_compute_verified", "actual_device": device, "gpu_name": props.name,
            "compute_capability": list(torch.cuda.get_device_capability(0)),
            "total_vram_mib": round(total_bytes / (1024 ** 2)),
            "free_vram_before_test_mib": round(free_bytes / (1024 ** 2)),
            "peak_test_tensor_allocation_mib": round(torch.cuda.max_memory_allocated(0) / (1024 ** 2), 2),
            "torch_version": torch.__version__, "torch_cuda_version": torch.version.cuda,
            "matrix_shape": [1024, 1024], "iterations": len(timings),
            "matrix_multiply_ms_median": round(statistics.median(timings), 3),
            "result_verified": True}


def run_check(timeout_seconds=90):
    try:
        completed = subprocess.run([sys.executable, "-m", "src.validation.gpu_check", "_run"],
                                   capture_output=True, text=True, timeout=timeout_seconds)
        if completed.returncode != 0:
            return {"status": "gpu_check_failed", "reason": "probe_process_failed"}
        report = json.loads(completed.stdout)
        if not isinstance(report, dict) or report.get("status") not in {"cuda_compute_verified", "gpu_check_failed"}:
            raise ValueError("Invalid probe response")
        return report
    except subprocess.TimeoutExpired:
        return {"status": "gpu_check_failed", "reason": "probe_timeout"}
    except (ValueError, OSError):
        return {"status": "gpu_check_failed", "reason": "probe_response_invalid"}


def main():
    if sys.argv[1:] == ["_run"]:
        try:
            with redirect_stdout(sys.stderr):
                report = probe()
        except Exception as error:
            # Never echo native driver errors, environment variables or local paths.
            report = {"status": "gpu_check_failed", "reason": "runtime_error", "error_type": type(error).__name__}
        print(json.dumps(report, allow_nan=False))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, choices=range(10, 181), default=90)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path; existing reports are never overwritten")
    report = run_check(args.timeout_seconds)
    report.update(scope="cuda_runtime_smoke", created_at=datetime.now(timezone.utc).isoformat(),
                  python_version=platform.python_version(), operating_system=platform.system(),
                  production_approved=False, model_loaded=False, camera_accessed=False,
                  accuracy_validated=False, camera_capacity_measured=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(report["status"])
    if report.get("reason"):
        print("Reason: " + report["reason"])
    if report["status"] == "cuda_compute_verified":
        print(f"GPU: {report['gpu_name']} | VRAM: {report['total_vram_mib']} MiB")
    return 0 if report["status"] == "cuda_compute_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
