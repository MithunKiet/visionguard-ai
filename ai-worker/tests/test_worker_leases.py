"""Bounded ownership despite HTTP delays, process restarts and capture hangs."""
import asyncio
from datetime import datetime, timedelta, timezone
import time
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.config import ownership
from src.config.ownership import bind_assignments, lease_valid, event_ownership, lease_clock, SESSION_ID, LeaseExpired
from src.pipeline.camera_worker import CameraWorker
from src.pipeline.frame_reader import CaptureProcess
from tests.test_capture_isolation import synthetic_stream, FRAME, DETECTIONS


def camera_grant():
    now = datetime.now(timezone.utc)
    return {"camera_id": str(uuid4()), "lease": {"token": str(uuid4()), "session_id": SESSION_ID,
        "generation": 1, "server_time": now.isoformat(), "expires_at": (now + timedelta(seconds=90)).isoformat(),
        "ttl_seconds": 90}}


def worker_with(lease):
    return CameraWorker(str(uuid4()), "rtsp://example.invalid/feed", {"required_consecutive_frames": 1},
        str(uuid4()), str(uuid4()), str(uuid4()), Mock(detect=AsyncMock(return_value=DETECTIONS)), lease=lease)


def test_network_delay_consumes_lease_and_wall_clock_does_not_extend_it(monkeypatch):
    camera = camera_grant()
    monkeypatch.setattr(ownership, "lease_clock", lambda: 20)
    bind_assignments([camera], 0)
    assert camera["lease"]["deadline"] == 85
    assert lease_valid(camera["lease"])
    monkeypatch.setattr(time, "time", lambda: -1000000)
    monkeypatch.setattr(ownership, "lease_clock", lambda: 86)
    assert not lease_valid(camera["lease"])
    with pytest.raises(LeaseExpired):
        event_ownership(camera["lease"])


def test_cache_cannot_resume_a_previous_process_or_unleased_camera():
    camera = bind_assignments([camera_grant()], lease_clock())[0]
    assert lease_valid(camera["lease"])
    camera["lease"]["session_id"] = str(uuid4())
    assert not lease_valid(camera["lease"])
    assert not lease_valid(None)
    with pytest.raises(ValueError):
        bind_assignments([camera], lease_clock())


@pytest.mark.parametrize("ttl", [float("inf"), float("nan"), 3600, -1, True])
def test_invalid_duration_fails_closed(ttl):
    camera = camera_grant()
    camera["lease"]["ttl_seconds"] = ttl
    with pytest.raises(ValueError):
        bind_assignments([camera], lease_clock())


@pytest.mark.asyncio
async def test_camera_expiry_cancels_hung_inference_without_assignment_poll(monkeypatch):
    lease = bind_assignments([camera_grant()], lease_clock())[0]["lease"]
    lease["deadline"] = lease_clock() + .15
    worker = worker_with(lease)
    started, stopped = asyncio.Event(), asyncio.Event()
    async def hung_pipeline():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            stopped.set()
    monkeypatch.setattr(worker, "_run", hung_pipeline)
    await asyncio.wait_for(worker.run(), 1)
    assert started.is_set() and stopped.is_set() and not worker._active


@pytest.mark.asyncio
async def test_inference_finishing_after_expiry_cannot_publish(monkeypatch):
    lease = bind_assignments([camera_grant()], lease_clock())[0]["lease"]
    worker = worker_with(lease)
    async def detect(*args, **kwargs):
        lease["deadline"] = lease_clock() - 1
        return DETECTIONS
    worker._detector.detect.side_effect = detect
    worker._publish_incident = AsyncMock()
    worker._publish = AsyncMock()
    await worker._process_frame(FRAME)
    worker._publish_incident.assert_not_awaited()
    worker._publish.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["hang_open", "hang_read", "hang_release"])
async def test_capture_child_exits_at_lease_deadline_without_parent_supervision(mode):
    capture = CaptureProcess(mode, 20, target=synthetic_stream, lease_deadline=lease_clock() + 1.5)
    try:
        # Block the parent event loop too: expiry is enforced in the child.
        time.sleep(2.2)
        assert not capture.process.is_alive()
    finally:
        await capture.stop()


@pytest.mark.asyncio
async def test_generation_change_reaps_old_pipeline_before_starting_new(monkeypatch):
    from src import main
    old = bind_assignments([camera_grant()], lease_clock())[0]
    old.update(rtsp_url="rtsp://example.invalid/feed", enterprise_id=str(uuid4()), factory_id=str(uuid4()), zone_id=str(uuid4()))
    stopped = asyncio.Event()
    class Pipeline:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.camera_id = kwargs["camera_id"]
        async def run(self):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
    monkeypatch.setattr(main, "CameraWorker", Pipeline)
    workers, tasks = [], {}
    await main.reconcile_cameras(workers, tasks, None, [old])
    await asyncio.sleep(0)
    new = {**old, "lease": {**old["lease"], "token": str(uuid4()), "generation": 2}}
    await main.reconcile_cameras(workers, tasks, None, [new])
    assert stopped.is_set() and len(workers) == 1 and workers[0].lease["token"] == new["lease"]["token"]
    await main.reconcile_cameras(workers, tasks, None, [])


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["expired", "previous_process", "legacy"])
async def test_reconciliation_cannot_start_cameras_from_unauthorized_cache(monkeypatch, mode):
    from src import main
    camera = bind_assignments([camera_grant()], lease_clock())[0]
    if mode == "expired":
        camera["lease"]["deadline"] = lease_clock() - 1
    elif mode == "previous_process":
        camera["lease"]["session_id"] = str(uuid4())
    else:
        camera.pop("lease")
    constructor = Mock()
    monkeypatch.setattr(main, "CameraWorker", constructor)
    workers, tasks = [], {}
    await main.reconcile_cameras(workers, tasks, None, [camera])
    assert workers == [] and tasks == {}
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_capture_watchdog_observes_renewal_without_reconnecting():
    capture = CaptureProcess("normal", 20, target=synthetic_stream, lease_deadline=lease_clock() + 1.5)
    try:
        await asyncio.sleep(.5)
        capture.lease_deadline.value = lease_clock() + 2
        await asyncio.sleep(1.2)
        assert capture.process.is_alive()  # Original deadline has passed.
        await asyncio.sleep(1.2)
        assert not capture.process.is_alive()
    finally:
        await capture.stop()
