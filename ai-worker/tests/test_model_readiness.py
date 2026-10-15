"""Runtime policy tests use explicit fake CUDA/model backends, never claim real GPU evidence."""
import asyncio
import hashlib
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from src.config.settings import settings
from src.pipeline.detector import PPEDetector, PPE_CLASSES
from src.pipeline.batch_detector import BatchDetector


class FakeModel:
    def __init__(self):
        self.names = dict(PPE_CLASSES)
        self.task = "detect"
        self.device = "cpu"
        self.predictor = None
        self.calls = []
        self.predictor_device = None
        self.failure = None

    def to(self, device):
        self.device = device

    def __call__(self, frames, **kwargs):
        self.calls.append((frames, kwargs))
        if self.failure:
            raise self.failure
        actual = self.predictor_device or kwargs["device"]
        self.predictor = SimpleNamespace(device=actual, model=SimpleNamespace(device=actual))
        return [SimpleNamespace(boxes=[], orig_shape=frame.shape[:2]) for frame in frames]


@pytest.fixture
def model_env(monkeypatch, tmp_path):
    weights = tmp_path / "ppe.pt"
    weights.write_bytes(b"test-only mocked checkpoint")
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "USE_GPU", True)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "ROBOFLOW_API_KEY", "")
    monkeypatch.setattr(settings, "YOLO_MODEL_PATH", str(weights))
    monkeypatch.setattr(settings, "YOLO_MODEL_SHA256", digest)
    model = FakeModel()
    loader = Mock(return_value=model)
    cuda = SimpleNamespace(is_available=Mock(return_value=True), device_count=Mock(return_value=1), synchronize=Mock())
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda))
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=loader))
    return SimpleNamespace(weights=weights, digest=digest, model=model, loader=loader, cuda=cuda)


def test_ready_requires_predictor_warmup_and_preserves_artifact_identity(model_env):
    detector = PPEDetector()
    assert detector.heartbeat_fields() == {"gpu_available": True, "model_version": "ppe:" + model_env.digest[:40]}
    assert detector.model_sha256 == model_env.digest
    assert len(detector.model_version) <= 50
    assert model_env.model.calls[0][0][0].shape == (640, 640, 3)
    assert model_env.model.calls[0][1]["device"] == "cuda:0"
    model_env.cuda.synchronize.assert_called_once_with(0)
    detector.detect_batch([np.zeros((32, 32, 3), dtype=np.uint8)])
    assert all(call[1]["device"] == "cuda:0" for call in model_env.model.calls)


@pytest.mark.parametrize("failure", ["unavailable", "zero_devices", "driver_error"])
def test_requested_cuda_never_falls_back_to_cpu(model_env, failure):
    if failure == "unavailable":
        model_env.cuda.is_available.return_value = False
    elif failure == "zero_devices":
        model_env.cuda.device_count.return_value = 0
    else:
        model_env.cuda.is_available.side_effect = RuntimeError("driver failure")
    with pytest.raises(RuntimeError):
        PPEDetector()
    model_env.loader.assert_not_called()


@pytest.mark.parametrize("policy", ["cpu", "demo", "missing_pin", "wrong_pin", "missing_weights_with_remote"])
def test_production_policy_fails_before_checkpoint_loading(model_env, monkeypatch, policy):
    if policy == "cpu":
        monkeypatch.setattr(settings, "USE_GPU", False)
    elif policy == "demo":
        monkeypatch.setattr(settings, "DEMO_MODE", True)
    elif policy == "missing_pin":
        monkeypatch.setattr(settings, "YOLO_MODEL_SHA256", "")
    elif policy == "wrong_pin":
        monkeypatch.setattr(settings, "YOLO_MODEL_SHA256", "0" * 64)
    else:
        model_env.weights.unlink()
        monkeypatch.setattr(settings, "ROBOFLOW_API_KEY", "test-only-no-network")
    with pytest.raises(RuntimeError):
        PPEDetector()
    model_env.loader.assert_not_called()


@pytest.mark.parametrize("invalid", ["missing_class", "extra_class", "swapped_classes", "wrong_task"])
def test_checkpoint_contract_is_exact(model_env, invalid):
    if invalid == "missing_class":
        model_env.model.names.pop(8)
    elif invalid == "extra_class":
        model_env.model.names[9] = "unreviewed_class"
    elif invalid == "swapped_classes":
        model_env.model.names[0], model_env.model.names[1] = model_env.model.names[1], model_env.model.names[0]
    else:
        model_env.model.task = "classify"
    with pytest.raises(RuntimeError):
        PPEDetector()
    assert not model_env.model.calls


@pytest.mark.parametrize("failure", ["wrong_model_device", "wrong_predictor_device", "warmup_error", "async_cuda_error"])
def test_loaded_weights_alone_do_not_establish_readiness(model_env, failure):
    if failure == "wrong_model_device":
        model_env.model.to = lambda device: None
    elif failure == "wrong_predictor_device":
        model_env.model.predictor_device = "cpu"
    elif failure == "warmup_error":
        model_env.model.failure = RuntimeError("warmup failed")
    else:
        model_env.cuda.synchronize.side_effect = RuntimeError("CUDA launch failure")
    with pytest.raises(RuntimeError):
        PPEDetector()


def test_explicit_development_cpu_reports_actual_device_even_if_setting_changes(model_env, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "USE_GPU", False)
    detector = PPEDetector()
    monkeypatch.setattr(settings, "USE_GPU", True)
    assert detector.heartbeat_fields()["gpu_available"] is False
    assert model_env.model.calls[0][1]["device"] == "cpu"
    model_env.cuda.synchronize.assert_not_called()


def test_runtime_inference_failure_revokes_readiness_until_restart(model_env):
    detector = PPEDetector()
    model_env.model.failure = RuntimeError("GPU execution failure")
    with pytest.raises(RuntimeError):
        detector.detect_batch([np.zeros((32, 32, 3), dtype=np.uint8)])
    with pytest.raises(RuntimeError, match="not ready"):
        detector.heartbeat_fields()
    model_env.model.failure = None
    with pytest.raises(RuntimeError, match="restart"):
        detector.detect_batch([np.zeros((32, 32, 3), dtype=np.uint8)])


def test_predictor_device_drift_revokes_heartbeat(model_env):
    detector = PPEDetector()
    model_env.model.predictor.model.device = "cpu"
    with pytest.raises(RuntimeError, match="requested inference device"):
        detector.heartbeat_fields()
    with pytest.raises(RuntimeError, match="not ready"):
        detector.heartbeat_fields()


@pytest.mark.asyncio
async def test_heartbeat_uses_runtime_fields_and_unready_runtime_never_posts(monkeypatch):
    from src import main as runtime
    post = AsyncMock(return_value=SimpleNamespace(raise_for_status=Mock()))
    client = AsyncMock()
    client.__aenter__.return_value = SimpleNamespace(post=post)
    monkeypatch.setattr(runtime.httpx, "AsyncClient", lambda: client)
    detector = SimpleNamespace(heartbeat_fields=Mock(return_value={"gpu_available": False, "model_version": "ppe:test-artifact"}))
    monkeypatch.setattr(settings, "USE_GPU", True)
    await runtime.register_worker(detector)
    body = post.await_args.kwargs["json"]
    assert body["gpu_available"] is False and body["model_version"] == "ppe:test-artifact"
    post.reset_mock()
    detector.heartbeat_fields.side_effect = RuntimeError("not ready")
    with pytest.raises(RuntimeError):
        await runtime.register_worker(detector)
    post.assert_not_awaited()
    assert runtime.model_ready._value.get() == 0


@pytest.mark.asyncio
async def test_initialization_runs_on_inference_executor_without_blocking_event_loop(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    thread_ids = []
    def model_factory():
        thread_ids.append(threading.get_ident())
        entered.set()
        release.wait(2)
        def detect(frames):
            thread_ids.append(threading.get_ident())
            return [[] for _ in frames]
        return SimpleNamespace(detect_batch=detect, heartbeat_fields=lambda: {"gpu_available": False, "model_version": "test"})
    monkeypatch.setattr("src.pipeline.detector.PPEDetector", model_factory)
    detector = BatchDetector()
    with pytest.raises(RuntimeError, match="not initialized"):
        detector.heartbeat_fields()
    initialization = asyncio.create_task(detector.initialize())
    try:
        async with asyncio.timeout(1):
            while not entered.is_set():
                await asyncio.sleep(.01)
        assert not initialization.done()
        release.set()
        await initialization
        assert await detector.detect(np.zeros((8, 8, 3), dtype=np.uint8)) == []
        assert thread_ids[0] == thread_ids[1] != threading.get_ident()
        detector._inference_started_at = time.monotonic() - settings.MODEL_STALL_SECONDS - 1
        with pytest.raises(RuntimeError, match="stalled"):
            detector.heartbeat_fields()
    finally:
        release.set()
        await initialization
        await detector.stop()


@pytest.mark.asyncio
async def test_startup_failure_closes_journal_without_registration_or_cameras(monkeypatch):
    from src import main as runtime
    detector = SimpleNamespace(initialize=AsyncMock(side_effect=RuntimeError("model not ready")), start=Mock(), stop=AsyncMock())
    sync = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(runtime, "BatchDetector", lambda: detector)
    monkeypatch.setattr(runtime, "ZoneConfigSync", lambda *a, **kw: sync)
    for name in ("init_publisher", "close_publisher", "register_worker", "fetch_assigned_cameras", "reconcile_cameras"):
        monkeypatch.setattr(runtime, name, AsyncMock())
    monkeypatch.setattr(runtime, "start_metrics_server", Mock())
    with pytest.raises(RuntimeError, match="model not ready"):
        await runtime.main()
    runtime.close_publisher.assert_awaited_once()
    runtime.register_worker.assert_not_awaited()
    runtime.fetch_assigned_cameras.assert_not_awaited()
    runtime.reconcile_cameras.assert_not_awaited()
    detector.start.assert_not_called()
    detector.stop.assert_awaited_once()
    sync.start.assert_not_awaited()


@pytest.mark.parametrize("failure", ["timeout", "bad_output", "process_crash"])
def test_readiness_probe_records_failure_and_preserves_previous_reports(tmp_path, monkeypatch, failure):
    import json
    import subprocess
    from src.validation import model_readiness
    weights = tmp_path / "test-only.pt"
    weights.write_bytes(b"not a model")
    output = tmp_path / "readiness.json"
    monkeypatch.setattr(sys, "argv", ["model_readiness", "--weights", str(weights), "--model-sha256", "0" * 64,
        "--device", "cuda", "--output", str(output)])
    if failure == "timeout":
        monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("private-sentinel", 120)))
    else:
        monkeypatch.setattr(subprocess, "run", Mock(return_value=SimpleNamespace(returncode=0 if failure == "bad_output" else -9,
                                                                              stdout="invalid private-sentinel")))
    with pytest.raises(SystemExit) as result:
        model_readiness.main()
    assert result.value.code == 2
    report = json.loads(output.read_text())
    assert report["production_approved"] is False and report["status"] != "model_ready"
    assert "private-sentinel" not in output.read_text()
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        model_readiness.main()
    assert output.read_bytes() == original


@pytest.mark.skipif(not os.environ.get("TEST_MODEL_CPU_SMOKE"), reason="Requires pinned CPU PyTorch/Ultralytics")
def test_actual_cpu_model_warmup_and_readiness_probe(tmp_path):
    import json
    import subprocess
    from pathlib import Path
    import ultralytics
    from ultralytics import YOLO
    import yaml
    import torch
    torch.set_num_threads(1)
    config = yaml.safe_load((Path(ultralytics.__file__).parent / "cfg/models/v8/yolov8.yaml").read_text())
    config["nc"] = 9
    config["scale"] = "n"
    architecture = tmp_path / "untrained-test-only.yaml"
    architecture.write_text(yaml.safe_dump(config))
    model = YOLO(str(architecture), task="detect")
    model.model.names = dict(PPE_CLASSES)
    checkpoint = tmp_path / "untrained-test-only.pt"
    model.save(str(checkpoint))
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    output = tmp_path / "readiness.json"
    result = subprocess.run([sys.executable, "-m", "src.validation.model_readiness", "--weights", str(checkpoint),
        "--model-sha256", digest, "--device", "cpu", "--output", str(output)],
        capture_output=True, text=True, timeout=140)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text())
    assert report["status"] == "model_ready" and report["actual_device"] == "cpu"
    assert report["gpu_available"] is False and report["production_approved"] is False
    assert report["model_sha256"] == digest and report["classes"] == list(PPE_CLASSES.values())
    # A pinned real artifact must still fail when CUDA is requested on this CPU-only runner.
    if not torch.cuda.is_available():
        failed = tmp_path / "cuda-unavailable.json"
        result = subprocess.run([sys.executable, "-m", "src.validation.model_readiness", "--weights", str(checkpoint),
            "--model-sha256", digest, "--device", "cuda", "--output", str(failed)],
            capture_output=True, text=True, timeout=140)
        assert result.returncode == 2 and json.loads(failed.read_text())["status"] == "model_readiness_failed"
