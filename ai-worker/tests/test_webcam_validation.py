import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.validation import camera


def fake_camera(monkeypatch, *, opened=True):
    import cv2
    cap = Mock()
    cap.isOpened.return_value = opened
    cap.get.return_value = 30
    cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    fake = SimpleNamespace(**{name: getattr(cv2, name) for name in [
        "CAP_ANY", "CAP_DSHOW", "CAP_MSMF", "CAP_PROP_FPS", "COLOR_BGR2GRAY", "WND_PROP_VISIBLE", "resize", "cvtColor"]})
    fake.VideoCapture = Mock(return_value=cap)
    fake.imshow = Mock()
    fake.waitKey = Mock(return_value=-1)
    fake.getWindowProperty = Mock(return_value=1)
    fake.destroyAllWindows = Mock()
    monkeypatch.setitem(__import__("sys").modules, "cv2", fake)
    monkeypatch.setattr(camera.sys, "platform", "win32")
    return cap, fake


@pytest.mark.parametrize("backend", ["directshow", "msmf"])
def test_windows_webcam_decode_releases_camera_and_saves_no_footage(monkeypatch, backend):
    cap, cv = fake_camera(monkeypatch)
    ticks = iter([0, 0, 0.1, 0.2, 0.3, 1.1, 1.2])
    monkeypatch.setattr(camera.time, "monotonic", lambda: next(ticks))
    report = camera.probe_worker({"camera_index": 1, "backend": backend, "seconds": 1})
    cv.VideoCapture.assert_called_once_with(1, cv.CAP_DSHOW if backend == "directshow" else cv.CAP_MSMF)
    assert report["status"] == "stream_measured"
    assert report["dimensions"] == {"640x480": 2}
    assert report["footage_saved"] is False
    assert report["accuracy_validated"] is False
    cap.release.assert_called_once()
    cv.imshow.assert_not_called()


@pytest.mark.parametrize("close_window", [False, True])
def test_preview_can_be_stopped_and_releases_resources(monkeypatch, close_window):
    cap, cv = fake_camera(monkeypatch)
    cv.waitKey.return_value = -1 if close_window else ord("q")
    cv.getWindowProperty.return_value = 0 if close_window else 1
    report = camera.probe_worker({"camera_index": 0, "backend": "directshow", "seconds": 30, "preview": True})
    assert report["status"] == "probe_cancelled"
    cv.imshow.assert_called_once()
    cap.release.assert_called_once()
    cv.destroyAllWindows.assert_called_once()


def test_camera_permission_failure_releases_device(monkeypatch):
    cap, _ = fake_camera(monkeypatch, opened=False)
    assert camera.probe_worker({"camera_index": 0, "backend": "directshow", "seconds": 1})["status"] == "unreachable"
    cap.release.assert_called_once()


def test_webcam_subprocess_is_bounded_and_cli_labels_report(monkeypatch, tmp_path):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout='{"status":"stream_measured","footage_saved":false}'))
    monkeypatch.setattr(camera.subprocess, "run", run)
    report = tmp_path / "webcam.json"
    monkeypatch.setattr(camera.sys, "argv", ["check", "webcam", "--camera-index", "1", "--backend", "msmf",
                                           "--seconds", "2", "--no-preview", "--output", str(report)])
    camera.main()
    config = json.loads(run.call_args.kwargs["input"])
    assert config == {"camera_index": 1, "seconds": 2, "backend": "msmf", "preview": False}
    assert run.call_args.kwargs["timeout"] == 27
    assert json.loads(report.read_text())["source"] == "local_webcam"
    assert json.loads(report.read_text())["camera_index"] == 1
    with pytest.raises(ValueError):
        camera.webcam_probe(-1, 30)


def test_device_read_failure_is_not_a_success(monkeypatch):
    cap, _ = fake_camera(monkeypatch)
    cap.read.return_value = (False, None)
    report = camera.probe_worker({"camera_index": 0, "backend": "msmf", "seconds": 1})
    assert report["status"] == "stream_incomplete"
    assert report["read_failed"] is True
    cap.release.assert_called_once()
