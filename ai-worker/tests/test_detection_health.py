"""Inference evidence follows accepted fresh results, never heartbeats alone."""
from unittest.mock import AsyncMock

import pytest

from src.config.ownership import lease_clock
from src.pipeline.batch_detector import DetectionExpired
from tests.test_capture_isolation import FRAME, DETECTIONS, packet
from tests.test_config_application import worker


@pytest.mark.asyncio
async def test_successful_fresh_frame_establishes_health_then_policy_change_clears_it():
    w = worker()
    w._detector.detect = AsyncMock(return_value=DETECTIONS)
    w._check_camera_spec = AsyncMock()
    w._publish_incident = AsyncMock()
    w._publish = AsyncMock()
    assert w.detection_health() == {"inference_age_seconds": None}
    await w._process_frame(FRAME)
    assert 0 <= w.detection_health()["inference_age_seconds"] < 1
    w.apply_zone_config({"version": 3, "required_ppe_types": ["helmet"]})
    assert w.detection_health()["inference_age_seconds"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "detector", "stream", "disabled", "stale"])
async def test_gaps_and_old_frames_cannot_renew_detection_evidence(failure):
    w = worker()
    w._detector.detect = AsyncMock(return_value=DETECTIONS)
    w._check_camera_spec = AsyncMock()
    w._publish = AsyncMock()
    w._publish_incident = AsyncMock()
    w._last_successful_inference = lease_clock()
    if failure == "timeout":
        w._detector.detect.side_effect = DetectionExpired()
        await w._process_frame(FRAME)
    elif failure == "detector":
        w._detector.detect.side_effect = RuntimeError("test inference failure")
        with pytest.raises(RuntimeError):
            await w._process_frame(FRAME)
    elif failure == "stream":
        await w._on_stream_status(True)
    elif failure == "disabled":
        w.set_active(False)
    else:
        w._last_successful_inference = lease_clock() - 31
        await w._process_frame(FRAME, packet=packet(age=100))
    assert w.detection_health()["inference_age_seconds"] is None
