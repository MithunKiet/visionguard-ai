import hashlib
import io
import os
import time
from unittest.mock import Mock

import numpy as np
import pytest

from src.validation import ppe_trial as trial


def test_rgb_letterbox_and_class_aware_nms_preserve_real_coordinates():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:, :, 2] = 255
    tensor, ratio, offset = trial.prepare_frame(frame)
    assert tensor.shape == (1, 3, 640, 640)
    assert tensor.dtype == np.float32
    assert ratio == 0.5 and offset == (0, 140)
    assert tensor[0, 0, 320, 320] == 1 and tensor[0, 2, 320, 320] == 0
    output = np.zeros((1, 10, 8400), dtype=np.float32)
    output[0, :4, :3] = np.array([320, 320, 100, 100])[:, None]
    output[0, 5, 0] = 0.9  # helmet
    output[0, 5, 1] = 0.8  # duplicate helmet
    output[0, 8, 2] = 0.9  # person: same box, different class must survive NMS
    results = trial.decode_predictions(output, frame.shape, ratio, offset, 0.5)
    assert [d["class_name"] for d in results] == ["helmet", "person"]
    assert results[0]["bbox"] == [540, 260, 740, 460]
    assert not any(d["class_name"] in {"nohelmet", "novest"} for d in results)


def test_no_candidates_does_not_imply_missing_ppe():
    assert trial.decode_predictions(np.zeros((1, 10, 8400)), (640, 640, 3), 1, (0, 0), 0.5) == []


@pytest.mark.parametrize("bad", [np.zeros((1, 6, 8400)), np.full((1, 10, 8400), np.nan)])
def test_invalid_model_output_fails_closed(bad):
    with pytest.raises(ValueError):
        trial.decode_predictions(bad, (640, 640, 3), 1, (0, 0), 0.5)


def test_download_verifies_checksum_and_cleans_up_failures(tmp_path, monkeypatch):
    target = tmp_path / "model.onnx"
    body = b"test-only-model-bytes"
    download = Mock(side_effect=lambda *args, **kwargs: io.BytesIO(body))
    monkeypatch.setattr(trial.urllib.request, "urlopen", download)
    with pytest.raises(ValueError, match="checksum"):
        trial.download_model(target)
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(trial, "MODEL_SHA256", hashlib.sha256(body).hexdigest())
    trial.download_model(target)
    assert target.read_bytes() == body
    download.reset_mock()
    trial.download_model(target)
    download.assert_not_called()
    target.write_bytes(b"corrupted")
    with pytest.raises(ValueError):
        trial.download_model(target)
    assert target.read_bytes() == b"corrupted"
    download.assert_not_called()


def test_local_trial_counts_predictions_without_approving_accuracy(monkeypatch):
    detector = Mock()
    detector.detect.return_value = [{"class_name": "nohelmet", "confidence": 0.9, "bbox": [1, 1, 20, 20]}]
    monkeypatch.setattr(trial, "TrialDetector", lambda: detector)
    cap = Mock()
    cap.isOpened.return_value = True
    def read():
        time.sleep(0.005)
        return True, np.zeros((64, 64, 3), dtype=np.uint8)
    cap.read.side_effect = read
    monkeypatch.setattr(trial.cv2, "VideoCapture", lambda *args: cap)
    monkeypatch.setattr(trial.cv2, "imshow", Mock())
    monkeypatch.setattr(trial.cv2, "waitKey", lambda *_: ord("q"))
    close = Mock()
    monkeypatch.setattr(trial.cv2, "destroyAllWindows", close)
    report = trial.trial_worker({"camera_index": 0, "backend": "directshow", "seconds": 2, "confidence": 0.5})
    assert report["status"] == "trial_stopped_by_user"
    assert report["processed_frames"] == 1
    assert report["detection_box_counts_across_frames"]["nohelmet"] == 1
    for key in ["accuracy_validated", "production_approved", "footage_saved", "frames_uploaded", "operational_alerts_sent"]:
        assert report[key] is False
    cap.release.assert_called_once()
    close.assert_called_once()


def test_camera_failure_does_not_report_a_success(monkeypatch):
    monkeypatch.setattr(trial, "TrialDetector", Mock())
    cap = Mock()
    cap.isOpened.return_value = False
    monkeypatch.setattr(trial.cv2, "VideoCapture", lambda *args: cap)
    assert trial.trial_worker({"camera_index": 0, "backend": "msmf"})["status"] == "camera_unavailable"
    cap.release.assert_called_once()


@pytest.mark.skipif(not os.environ.get("TEST_PPE_ONNX"), reason="Optional checksum-pinned real ONNX inference smoke")
def test_pinned_model_runs_locally_on_a_blank_frame():
    detector = trial.TrialDetector(os.environ["TEST_PPE_ONNX"])
    assert detector.detect(np.zeros((720, 1280, 3), dtype=np.uint8)) == []
