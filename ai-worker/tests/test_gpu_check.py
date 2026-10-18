"""Probe orchestration tests; mocked CUDA is never hardware acceptance evidence."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.validation import gpu_check


@pytest.fixture
def runtime(monkeypatch):
    tensor = Mock()
    tensor.device = "cuda:0"
    # A tiny stand-in exercises control flow without installing GPU packages in CI.
    class Matrix:
        def __matmul__(self, other):
            return tensor

    cuda = SimpleNamespace(is_available=Mock(return_value=True), device_count=Mock(return_value=1),
        get_device_properties=Mock(return_value=SimpleNamespace(name="Test GPU")),
        mem_get_info=Mock(return_value=(6 * 1024 ** 3, 8 * 1024 ** 3)), reset_peak_memory_stats=Mock(),
        synchronize=Mock(), get_device_capability=Mock(return_value=(8, 9)),
        max_memory_allocated=Mock(return_value=16 * 1024 ** 2))
    from contextlib import nullcontext
    torch = SimpleNamespace(cuda=cuda, __version__="test", version=SimpleNamespace(cuda="test"),
        inference_mode=nullcontext, float32="float32", ones=Mock(return_value=Matrix()),
        ones_like=Mock(return_value=Matrix()), full_like=Mock(return_value=object()), allclose=Mock(return_value=True))
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch, tensor


def test_cuda_computation_is_synchronized_and_checked(runtime):
    torch, _ = runtime
    result = gpu_check.probe()
    assert result["status"] == "cuda_compute_verified"
    assert result["total_vram_mib"] == 8192
    assert result["iterations"] == 10 and result["result_verified"] is True
    torch.ones.assert_called_once_with((1024, 1024), dtype="float32", device="cuda:0")
    torch.full_like.assert_called_once()
    assert torch.cuda.synchronize.call_count == 11
    torch.allclose.assert_called_once()


@pytest.mark.parametrize("failure", ["no_cuda", "no_devices", "wrong_result", "wrong_device"])
def test_unavailable_or_incorrect_cuda_never_passes(runtime, failure):
    torch, tensor = runtime
    if failure == "no_cuda":
        torch.cuda.is_available.return_value = False
    elif failure == "no_devices":
        torch.cuda.device_count.return_value = 0
    elif failure == "wrong_result":
        torch.allclose.return_value = False
    else:
        tensor.device = "cpu"
    assert gpu_check.probe()["status"] == "gpu_check_failed"
    if failure in {"no_cuda", "no_devices"}:
        torch.ones.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "crash", "invalid_json", "invalid_status", "not_object"])
def test_native_subprocess_failures_are_bounded_and_sanitized(monkeypatch, failure):
    result = SimpleNamespace(returncode=0, stdout='{"status":"gpu_check_failed","reason":"cuda_unavailable"}')
    run = Mock(return_value=result)
    if failure == "timeout":
        run.side_effect = subprocess.TimeoutExpired("secret-native-path", 12)
    elif failure == "crash":
        result.returncode = 1
    elif failure == "invalid_json":
        result.stdout = "secret-native-path"
    elif failure == "invalid_status":
        result.stdout = '{"status":"unknown"}'
    else:
        result.stdout = "[]"
    monkeypatch.setattr(gpu_check.subprocess, "run", run)
    report = gpu_check.run_check(12)
    assert report["status"] == "gpu_check_failed"
    assert "secret-native-path" not in json.dumps(report)
    assert run.call_args.kwargs["timeout"] == 12


def test_native_exception_does_not_leak_details(monkeypatch, capsys):
    monkeypatch.setattr(gpu_check.sys, "argv", ["gpu_check", "_run"])
    monkeypatch.setattr(gpu_check, "probe", Mock(side_effect=RuntimeError("secret-native-path")))
    assert gpu_check.main() == 0  # Parent uses the structured failed status.
    text = capsys.readouterr().out
    assert json.loads(text)["status"] == "gpu_check_failed"
    assert "secret-native-path" not in text


def test_report_preserves_scope_and_never_overwrites(monkeypatch, tmp_path):
    output = tmp_path / "gpu.json"
    monkeypatch.setattr(gpu_check.sys, "argv", ["gpu_check", "--output", str(output)])
    monkeypatch.setattr(gpu_check, "run_check", Mock(return_value={"status": "cuda_compute_verified",
        "gpu_name": "Test GPU", "total_vram_mib": 8192}))
    assert gpu_check.main() == 0
    report = json.loads(output.read_text())
    assert report["scope"] == "cuda_runtime_smoke"
    for key in ("production_approved", "model_loaded", "camera_accessed", "accuracy_validated", "camera_capacity_measured"):
        assert report[key] is False
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        gpu_check.main()
    assert output.read_bytes() == original


def test_real_cli_without_torch_writes_failed_report(tmp_path):
    # python -S bypasses site-packages, so this exercises a real clean subprocess
    # on Linux and Windows without depending on the test runner's installed torch.
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    (tmp_path / "torch.py").write_text('raise ImportError("test-only missing GPU runtime")\n')
    report = tmp_path / "gpu.json"
    worker_root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", "-m", "src.validation.gpu_check",
        "--output", str(report)], cwd=worker_root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert json.loads(report.read_text())["status"] == "gpu_check_failed"
    assert "test-only missing GPU runtime" not in result.stdout + result.stderr
