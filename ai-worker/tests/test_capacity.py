import asyncio
import threading
from unittest.mock import Mock

import numpy as np
import pytest

from src.capacity.benchmark import measure
from src.pipeline.batch_detector import BatchDetector, DetectionOverloaded

FRAME = np.zeros((32, 32, 3), dtype=np.uint8)


@pytest.mark.asyncio
async def test_batched_results_stay_paired_with_requests():
    model = Mock(detect_batch=lambda frames: [[int(frame[0, 0, 0])] for frame in frames])
    detector = BatchDetector(model)
    try:
        assert await asyncio.gather(*(detector.detect(FRAME + i) for i in range(4))) == [[0], [1], [2], [3]]
    finally:
        await detector.stop()


@pytest.mark.asyncio
async def test_wrong_result_count_fails_all_requests_instead_of_hanging():
    detector = BatchDetector(Mock(detect_batch=lambda frames: []))
    try:
        results = await asyncio.gather(*(detector.detect(FRAME) for _ in range(3)), return_exceptions=True)
        assert all(isinstance(result, ValueError) for result in results)
    finally:
        await detector.stop()


@pytest.mark.asyncio
async def test_overload_is_bounded_and_cancelled_frames_are_not_inferred():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def blocked(frames):
        calls.append(len(frames))
        entered.set()
        release.wait(2)
        return [[] for _ in frames]
    detector = BatchDetector(Mock(detect_batch=blocked), queue_size=1, timeout=3)
    first = asyncio.create_task(detector.detect(FRAME))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        second = asyncio.create_task(detector.detect(FRAME))
        await asyncio.sleep(0)
        with pytest.raises(DetectionOverloaded):
            await detector.detect(FRAME)
        assert detector._queue.qsize() == 1
        second.cancel()
        await asyncio.gather(second, return_exceptions=True)
        release.set()
        await first
        await asyncio.sleep(0.07)
        assert calls == [1]
    finally:
        release.set()
        await detector.stop()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)


@pytest.mark.asyncio
async def test_timeout_and_shutdown_release_waiters():
    detector = BatchDetector(Mock(detect_batch=lambda frames: [[] for _ in frames]), timeout=0.001)
    try:
        with pytest.raises(asyncio.TimeoutError):
            await detector.detect(FRAME)
    finally:
        await detector.stop()
    with pytest.raises(RuntimeError):
        await detector.detect(FRAME)
    detector = BatchDetector(Mock(detect_batch=lambda frames: [[] for _ in frames]))
    pending = asyncio.create_task(detector.detect(FRAME))
    await asyncio.sleep(0)
    await detector.stop()
    assert isinstance((await asyncio.gather(pending, return_exceptions=True))[0], asyncio.CancelledError)


@pytest.mark.asyncio
async def test_load_sweep_exposes_per_camera_starvation_even_when_others_are_fast():
    class Uneven:
        async def detect(self, frame, camera_id):
            if camera_id.endswith("1"):
                await asyncio.sleep(0.08)
            return []
    report = await measure(Uneven(), [FRAME], 2, 40, 0.2, 20, 0.8)
    assert report["inference_targets_met"] is False
    assert report["per_camera"][0]["achieved_fps"] > report["per_camera"][1]["achieved_fps"]
    assert report["per_camera"][1]["missed_schedule_slots"] > 0


@pytest.mark.asyncio
async def test_load_sweep_counts_inference_failures():
    class Broken:
        async def detect(self, frame, camera_id):
            raise RuntimeError("test-only failure")
    report = await measure(Broken(), [FRAME], 1, 20, 0.1, 500, 0.95)
    assert report["per_camera"][0]["failures"] > 0
    assert report["per_camera"][0]["p95_ms"] is None
    assert report["inference_targets_met"] is False


def test_benchmark_images_are_local_and_reports_use_hashes(tmp_path):
    import hashlib
    import json
    import cv2
    from src.capacity.benchmark import load_images
    content = cv2.imencode(".png", FRAME)[1].tobytes()
    (tmp_path / "image.png").write_bytes(content)
    manifest = tmp_path / "frames.json"
    manifest.write_text(json.dumps({"images": ["image.png"]}))
    frames, records = load_images(manifest)
    assert frames[0].shape == FRAME.shape
    assert records == [{"sha256": hashlib.sha256(content).hexdigest(), "width": 32, "height": 32}]
    manifest.write_text(json.dumps({"images": ["../outside.png"]}))
    with pytest.raises(ValueError):
        load_images(manifest)


@pytest.mark.asyncio
async def test_benchmark_rejects_unverified_weights_before_model_loading(tmp_path):
    from src.capacity.benchmark import run
    weights = tmp_path / "test-only.pt"
    weights.write_bytes(b"not a checkpoint")
    with pytest.raises(ValueError, match="checksum"):
        await run({"weights": str(weights), "model_sha256": "0" * 64})


def test_benchmark_timeout_is_not_capacity_evidence_and_existing_reports_survive(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys
    from src.capacity.benchmark import main
    weights = tmp_path / "test-only.pt"
    weights.touch()
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{}')
    output = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["benchmark", "--weights", str(weights), "--model-sha256", "0" * 64,
        "--manifest", str(manifest), "--device", "cpu", "--output", str(output)])
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("private-sentinel", 1)))
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
    assert json.loads(output.read_text())["status"] == "benchmark_timeout"
    assert json.loads(output.read_text())["production_approved"] is False
    assert "private-sentinel" not in output.read_text()
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        main()
    assert output.read_bytes() == original


def test_inference_gap_breaks_voting_without_removing_delivery_cooldown():
    from src.pipeline.ppe_validator import PPEValidator
    from src.pipeline.types import Detection
    validator = PPEValidator()
    detections = [Detection("person", 0.95, (0, 0, 100, 200), False),
                  Detection("no_helmet", 0.95, (0, 0, 100, 200), True)]
    config = {"required_consecutive_frames": 3}
    assert validator.evaluate(detections, config) == []
    assert validator.evaluate(detections, config) == []
    validator.mark_gap()
    assert validator.evaluate(detections, config) == []
    assert validator.evaluate(detections, config) == []
    assert validator.evaluate(detections, config)
    validator.mark_gap()
    for _ in range(4):
        assert validator.evaluate(detections, config) == []
