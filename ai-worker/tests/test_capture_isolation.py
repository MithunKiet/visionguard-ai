"""Real spawned capture children plus deterministic inference freshness regressions."""
import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
import os
import signal
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import numpy as np
import pytest

from src.config.settings import settings
from src.pipeline import frame_reader as readers
from src.pipeline.batch_detector import BatchDetector, DetectionExpired
from src.pipeline.camera_worker import CameraWorker
from src.pipeline.capture_process import capture_stream
from src.pipeline.frame_reader import CaptureProcess, CapturedFrame, FrameReader
from src.pipeline.types import Detection

FRAME = np.zeros((8, 8, 3), dtype=np.uint8)
DETECTIONS = [Detection("person", .99, (0, 0, 100, 200), False),
              Detection("no_helmet", .99, (0, 0, 100, 200), True)]


def hang():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1)


class SyntheticCapture:
    def __init__(self, url, transport):
        self.mode = url
        self.count = 0
        if url == "hang_open":
            hang()

    def isOpened(self):
        return True

    def get(self, key):
        return 100

    def read(self):
        self.count += 1
        if self.mode == "hang_read" and self.count > 1:
            hang()
        if self.mode == "hang_release" and self.count > 1:
            return False, None
        time.sleep(.01)
        shape = (32, 32, 3) if self.mode == "oversize" else FRAME.shape
        return True, np.full(shape, self.count % 255, dtype=np.uint8)

    def release(self):
        if self.mode == "hang_release":
            hang()


def synthetic_stream(*args):
    capture_stream(*args, opener=SyntheticCapture)


def locked_stream(url, transport, pixels, metadata, lock, sample_fps):
    lock.acquire()
    hang()


@pytest.fixture
def capture_settings(monkeypatch):
    monkeypatch.setattr(settings, "CAPTURE_MAX_FRAME_BYTES", FRAME.nbytes)
    monkeypatch.setattr(settings, "CAPTURE_STALL_SECONDS", 3)
    monkeypatch.setattr(settings, "CAPTURE_STOP_TIMEOUT_SECONDS", .1)
    monkeypatch.setattr(readers, "RECONNECT_DELAYS", [.02, .03, .04])


def factory(url, fps):
    return CaptureProcess(url, fps, target=synthetic_stream)


async def eventually(predicate, timeout=6):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.01)


def assert_reaped(pid):
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_slow_consumer_gets_latest_frame_and_sampling_changes_without_reconnect(capture_settings):
    reader = FrameReader(str(uuid4()), "healthy", 20, process_factory=factory)
    async with aclosing(reader.read_frames()) as frames:
        first = await asyncio.wait_for(anext(frames), 6)
        pid = reader._capture.process.pid
        await asyncio.sleep(.3)
        latest = await anext(frames)
        assert latest.image[0, 0, 0] > first.image[0, 0, 0] + 10
        assert time.monotonic() - latest.received_at < .2
        assert reader._latest is None
        reader.set_sample_fps(1)
        await asyncio.sleep(.1)
        sample = await anext(frames)
        next_sample = await asyncio.wait_for(anext(frames), 2)
        assert next_sample.received_at - sample.received_at >= .9
        assert reader._capture.process.pid == pid
    assert reader._capture is None
    assert_reaped(pid)


@pytest.mark.parametrize("mode", ["hang_open", "hang_read", "hang_release", "locked"])
@pytest.mark.asyncio
async def test_stalled_child_is_reaped_before_reconnect_and_other_camera_keeps_progressing(capture_settings, mode):
    attempts, old_pids = [], []
    def recovering_factory(url, fps):
        for pid in old_pids:
            assert_reaped(pid)
        capture = CaptureProcess(mode if not attempts else "healthy", fps,
                                 target=locked_stream if mode == "locked" and not attempts else synthetic_stream)
        attempts.append(capture)
        old_pids.append(capture.process.pid)
        return capture
    statuses = []
    async def status(offline):
        statuses.append(offline)
    troubled = FrameReader(str(uuid4()), "private-test-source", 20, on_status=status, process_factory=recovering_factory)
    healthy = FrameReader(str(uuid4()), "healthy", 20, process_factory=factory)
    try:
        await troubled.start()
        await healthy.start()
        await eventually(lambda: healthy._latest is not None)
        first = healthy._latest.received_at
        await eventually(lambda: len(attempts) >= 2 and troubled._connected)
        assert healthy._latest.received_at > first + .3
        assert statuses == [True, False]
        assert troubled._latest.generation == 2
        assert len(attempts) == 2
    finally:
        await asyncio.gather(troubled.stop(), healthy.stop())
    for pid in old_pids:
        assert_reaped(pid)


@pytest.mark.asyncio
async def test_oversized_frames_are_rejected_without_pixels_or_connected_state(capture_settings):
    reader = FrameReader(str(uuid4()), "oversize", 20, process_factory=factory)
    try:
        await reader.start()
        await eventually(lambda: reader._failure_count >= 1)
        assert reader._latest is None and not reader._connected
        assert reader.stream_width is None
    finally:
        await reader.stop()


def make_worker():
    worker = CameraWorker(str(uuid4()), "rtsp://example.invalid/feed", {"required_consecutive_frames": 1},
        str(uuid4()), str(uuid4()), str(uuid4()), SimpleNamespace(detect=AsyncMock(return_value=DETECTIONS)))
    worker._check_camera_spec = AsyncMock()
    worker._publish_occupancy = AsyncMock()
    worker._reader._connected = True
    worker._reader._generation = 1
    return worker


def packet(age=0, generation=1):
    return CapturedFrame(FRAME.copy(), time.monotonic() - age, time.time() - age, generation)


@pytest.mark.asyncio
async def test_cancellation_during_inference_closes_generator_and_capture_process(capture_settings):
    worker = make_worker()
    worker._reader = FrameReader(worker.camera_id, "healthy", 20, process_factory=factory)
    entered = asyncio.Event()
    async def processing(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    worker._process_frame = processing
    task = asyncio.create_task(worker.run())
    try:
        await asyncio.wait_for(entered.wait(), 6)
        pid = worker._reader._capture.process.pid
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)
        assert worker._reader._capture is None and worker._reader._task is None
        assert_reaped(pid)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("age,generation", [(10, 1), (-10, 1), (0, 0)])
@pytest.mark.asyncio
async def test_stale_or_old_connection_frame_never_reaches_inference(age, generation):
    worker = make_worker()
    worker._validator.mark_gap = Mock(wraps=worker._validator.mark_gap)
    await worker._process_frame(FRAME, packet=packet(age, generation))
    worker._detector.detect.assert_not_awaited()
    worker._publish_occupancy.assert_not_awaited()
    worker._validator.mark_gap.assert_called_once()


@pytest.mark.parametrize("change", ["age", "disable", "config", "reconnect"])
@pytest.mark.asyncio
async def test_late_or_superseded_inference_cannot_emit_events(monkeypatch, change):
    worker = make_worker()
    publish = AsyncMock()
    monkeypatch.setattr("src.pipeline.camera_worker.publish_incident", publish)
    monkeypatch.setattr(settings, "FRAME_MAX_AGE_SECONDS", .1)
    async def inference(*args, **kwargs):
        if change == "age":
            await asyncio.sleep(.12)
        elif change == "disable":
            worker.set_active(False)
        elif change == "config":
            worker.apply_zone_config({"version": 2, "ppe_required": []})
        else:
            worker._reader._generation += 1
        return DETECTIONS
    worker._detector.detect.side_effect = inference
    await worker._process_frame(FRAME, packet=packet())
    publish.assert_not_awaited()
    worker._publish_occupancy.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_event_keeps_local_decode_timestamp(monkeypatch):
    worker = make_worker()
    publish = AsyncMock()
    monkeypatch.setattr("src.pipeline.camera_worker.publish_incident", publish)
    sample = packet(.1)
    await worker._process_frame(FRAME, packet=sample)
    assert publish.await_count == 1
    assert publish.await_args.args[1]["timestamp"] == datetime.fromtimestamp(sample.received_wall_time, timezone.utc).isoformat()
    assert worker._detector.detect.await_args.kwargs["deadline"] == sample.received_at + settings.FRAME_MAX_AGE_SECONDS


@pytest.mark.asyncio
async def test_expired_queued_frames_do_not_consume_model_capacity():
    entered, release = threading.Event(), threading.Event()
    seen = []
    def model(frames):
        seen.extend(int(frame[0, 0, 0]) for frame in frames)
        entered.set()
        release.wait(2)
        return [[] for frame in frames]
    detector = BatchDetector(Mock(detect_batch=model), timeout=3)
    first = asyncio.create_task(detector.detect(FRAME))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(DetectionExpired):
            await detector.detect(FRAME + 1, deadline=time.monotonic() + .1)
        release.set()
        await first
        await detector.detect(FRAME + 2, deadline=time.monotonic() + 1)
        assert seen == [0, 2]
        with pytest.raises(DetectionExpired):
            await detector.detect(FRAME + 3, deadline=time.monotonic() - 1)
        assert seen == [0, 2]
    finally:
        release.set()
        await detector.stop()
        await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
async def test_assignment_revocation_cancels_all_cameras_before_waiting_for_cleanup():
    from src.main import reconcile_cameras
    cancelled = set()
    both_cancelled = asyncio.Event()
    async def run(camera_id):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.add(camera_id)
            if len(cancelled) == 2:
                both_cancelled.set()
            await both_cancelled.wait()
    workers = [SimpleNamespace(camera_id=str(uuid4()), rtsp_url="rtsp://example.invalid/feed") for _ in range(2)]
    tasks = {worker.camera_id: asyncio.create_task(run(worker.camera_id)) for worker in workers}
    original_tasks = list(tasks.values())
    await asyncio.sleep(0)
    try:
        await asyncio.wait_for(reconcile_cameras(workers, tasks, None, []), 1)
        assert not workers and not tasks and len(cancelled) == 2
    finally:
        both_cancelled.set()
        for task in original_tasks:
            task.cancel()
        await asyncio.gather(*original_tasks, return_exceptions=True)


@pytest.mark.skipif(not os.environ.get("TEST_CAPTURE_RTSP_URL"), reason="Requires an authorized or synthetic RTSP source")
@pytest.mark.asyncio
async def test_native_rtsp_capture_stays_fresh_with_a_slow_consumer():
    reader = FrameReader(str(uuid4()), os.environ["TEST_CAPTURE_RTSP_URL"], 10)
    async with aclosing(reader.read_frames()) as frames:
        first = await asyncio.wait_for(anext(frames), 20)
        pid = reader._capture.process.pid
        assert first.image.ndim == 3 and first.image.size > 0
        await asyncio.sleep(1)
        latest = await asyncio.wait_for(anext(frames), 5)
        assert latest.received_at > first.received_at + .5
        assert time.monotonic() - latest.received_at < .5
        assert reader._capture.process.pid == pid
    assert_reaped(pid)


@pytest.mark.asyncio
async def test_inference_uses_dedicated_executor_when_default_pool_is_busy():
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_running_loop()
    previous = loop._default_executor
    pool = ThreadPoolExecutor(max_workers=1)
    entered, release = threading.Event(), threading.Event()
    def blocked_storage():
        entered.set()
        release.wait(3)
    loop.set_default_executor(pool)
    blocked = asyncio.create_task(asyncio.to_thread(blocked_storage))
    detector = BatchDetector(Mock(detect_batch=lambda frames: [[] for _ in frames]), timeout=1)
    try:
        await eventually(entered.is_set, timeout=1)
        assert await detector.detect(FRAME, deadline=time.monotonic() + .5) == []
        assert not blocked.done()
    finally:
        release.set()
        await blocked
        await detector.stop()
        loop._default_executor = previous
        pool.shutdown(wait=True)
