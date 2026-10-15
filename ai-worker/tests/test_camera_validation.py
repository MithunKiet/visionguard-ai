import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.validation.camera import evaluate, load_manifest, probe, main
from src.validation.metrics import read_yolo_labels, score_frame, summarize


CLASSES = ["no_helmet", "no_vest"]


def detection(name="no_helmet", confidence=0.9, box=(0, 0, 100, 100)):
    return {"class_name": name, "bbox": box, "confidence": confidence}


def test_matching_counts_duplicates_misses_wrong_classes_and_negative_frames():
    truth = [detection(), detection("no_vest", box=(200, 0, 300, 100))]
    scored = score_frame(truth, [detection(), detection(), detection("no_vest", box=(400, 0, 500, 100))], CLASSES)
    assert scored == {"no_helmet": {"tp": 1, "fp": 1, "fn": 0}, "no_vest": {"tp": 0, "fp": 1, "fn": 1}}
    assert score_frame([], [detection()], CLASSES)["no_helmet"]["fp"] == 1
    assert score_frame([detection()], [detection("no_vest")], CLASSES)["no_helmet"]["fn"] == 1
    assert score_frame([detection()], [detection(confidence=0.59)], CLASSES)["no_helmet"] == {"tp": 0, "fp": 0, "fn": 1}
    assert summarize(scored)["no_helmet"]["precision"] == 0.5


def test_empty_classes_never_report_perfect_accuracy():
    empty = summarize(score_frame([], [], CLASSES))
    assert empty["no_helmet"]["precision"] is None
    assert empty["no_helmet"]["recall"] is None


@pytest.mark.parametrize("box", [(0, 0, 0, 1), (2, 2, 1, 1), (0, 0, float("nan"), 1), (-1, 0, 2, 2)])
def test_invalid_geometry_fails(box):
    with pytest.raises(ValueError):
        score_frame([], [detection(box=box)], CLASSES)


def test_label_missing_is_not_treated_as_a_clean_frame(tmp_path):
    labels = tmp_path / "labels.txt"
    with pytest.raises(FileNotFoundError):
        read_yolo_labels(labels, 100, 100, CLASSES)
    labels.write_text("")
    assert read_yolo_labels(labels, 100, 100, CLASSES) == []
    labels.write_text("0 0.5 0.5 0.4 0.4\n")
    assert read_yolo_labels(labels, 100, 100, CLASSES)[0]["bbox"] == [30, 30, 70, 70]
    labels.write_text("0 0.9 0.5 0.4 0.4\n")
    with pytest.raises(ValueError):
        read_yolo_labels(labels, 100, 100, CLASSES)


def manifest(tmp_path):
    (tmp_path / "image.jpg").touch()
    (tmp_path / "label.txt").touch()
    path = tmp_path / "manifest.json"
    data = {"dataset_id": "test", "source": "real_camera", "split": "held_out", "frames": [{
        "image": "image.jpg", "label": "label.txt", "camera_id": "camera-1", "session_id": "shift-1", "condition": "day"}]}
    path.write_text(json.dumps(data))
    return path, data


@pytest.mark.parametrize("case", ["missing_label", "traversal", "duplicate", "not_held_out", "synthetic", "empty"])
def test_manifest_rejects_incomplete_or_mislabeled_evidence(tmp_path, case):
    path, data = manifest(tmp_path)
    assert load_manifest(path)["dataset_id"] == "test"
    if case == "missing_label":
        (tmp_path / "label.txt").unlink()
    elif case == "traversal":
        data["frames"][0]["image"] = "../private.jpg"
    elif case == "duplicate":
        data["frames"] *= 2
    elif case == "not_held_out":
        data["split"] = "train"
    elif case == "synthetic":
        data["source"] = "simulator"
    else:
        data["frames"] = []
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_manifest(path)


def test_probe_keeps_url_out_of_argv_and_bounds_native_process(monkeypatch):
    secret_url = "rtsp://test:private-sentinel@camera.invalid/live"
    monkeypatch.setenv("TEST_CAMERA_URL", secret_url)
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout='{"status":"stream_measured"}'))
    monkeypatch.setattr(subprocess, "run", run)
    assert probe("TEST_CAMERA_URL", 2)["status"] == "stream_measured"
    args, kwargs = run.call_args
    assert secret_url not in " ".join(args[0])
    assert json.loads(kwargs["input"])["url"] == secret_url
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["timeout"] == 27
    run.side_effect = subprocess.TimeoutExpired("private-sentinel", 27)
    assert probe("TEST_CAMERA_URL", 2)["status"] == "probe_timeout"


def test_cli_failure_never_prints_private_input_or_overwrites_evidence(monkeypatch, tmp_path, capsys):
    output = tmp_path / "report.json"
    monkeypatch.setenv("TEST_CAMERA_URL", "https://test:private-sentinel@camera.invalid")
    monkeypatch.setattr("sys.argv", ["validation", "probe", "--url-env", "TEST_CAMERA_URL", "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "private-sentinel" not in capsys.readouterr().err
    assert not output.exists()
    output.write_text("preserved")
    with pytest.raises(SystemExit):
        main()
    assert Path(output).read_text() == "preserved"


def test_evaluation_uses_all_labels_and_disables_remote_and_demo(monkeypatch, tmp_path):
    import cv2
    import numpy as np
    from src.config.settings import settings
    from src.pipeline.types import Detection

    path, _ = manifest(tmp_path)
    cv2.imwrite(str(tmp_path / "image.jpg"), np.zeros((100, 100, 3), dtype=np.uint8))
    (tmp_path / "label.txt").write_text("0 0.5 0.5 1 1\n")
    weights = tmp_path / "test-only-model.pt"
    weights.write_bytes(b"Test mock, not real weights")
    for name in ["YOLO_MODEL_PATH", "DEMO_MODE", "ROBOFLOW_API_KEY", "USE_GPU"]:
        monkeypatch.setattr(settings, name, getattr(settings, name))
    def make_detector():
        assert settings.DEMO_MODE is False
        assert settings.ROBOFLOW_API_KEY == ""
        return SimpleNamespace(_model=SimpleNamespace(device="cpu"), detect=lambda frame: [
            Detection("no_helmet", 0.9, (0, 0, 100, 100), True), Detection("no_vest", 0.9, (0, 0, 100, 100), True)])
    monkeypatch.setitem(__import__("sys").modules, "src.pipeline.detector", SimpleNamespace(
        PPEDetector=make_detector, PPE_CLASSES=dict(enumerate(CLASSES))))
    result = evaluate(path, weights, 0.6, 0.5, "cpu")
    assert result["classes"]["no_helmet"]["tp"] == 1
    assert result["classes"]["no_vest"]["fp"] == 1
    assert result["unobserved_classes"] == ["no_vest"]
    assert result["production_approved"] is False
    assert result["temporal_alert_pipeline_validated"] is False
    assert result["by_condition"]["day"] == result["classes"]
    (tmp_path / "label.txt").write_text("")
    changed = evaluate(path, weights, 0.6, 0.5, "cpu")
    assert result["dataset_content_sha256"] != changed["dataset_content_sha256"]
    assert changed["classes"]["no_helmet"]["fp"] == 1
