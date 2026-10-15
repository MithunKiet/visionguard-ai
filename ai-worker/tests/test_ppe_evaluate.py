import json
import os
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from src.validation import ppe_evaluate as evaluator
from src.validation.ppe_trial import NAMES


def dataset(tmp_path):
    manifest = {"dataset_id": "test-fixture", "source": "real_camera", "split": "held_out",
                "classes": list(NAMES), "frames": []}
    for index, condition in enumerate(["day", "dim"]):
        # Synthetic pixels exercise report plumbing, not camera accuracy.
        image = f"frame-{index}.png"
        label = f"frame-{index}.txt"
        (tmp_path / image).write_bytes(cv2.imencode(".png", np.full((100, 100, 3), index, dtype=np.uint8))[1].tobytes())
        (tmp_path / label).write_text("1 0.5 0.5 1 1\n" if index == 0 else "")
        manifest["frames"].append({"image": image, "label": label, "camera_id": "test-camera",
                                   "session_id": f"session-{index}", "condition": condition})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def prediction(name, confidence=0.9):
    return {"class_name": name, "confidence": confidence, "bbox": [0, 0, 100, 100]}


def test_evaluation_counts_wrong_classes_negative_frames_and_condition_coverage(tmp_path, monkeypatch):
    path, _ = dataset(tmp_path)
    detector = Mock()
    detector.detect.side_effect = [[prediction("helmet"), prediction("novest")], [prediction("helmet")]]
    monkeypatch.setattr(evaluator, "TrialDetector", lambda: detector)
    report = evaluator.evaluate(path)
    assert report["classes"]["helmet"] == {"tp": 1, "fp": 1, "fn": 0, "support": 1, "precision": 0.5, "recall": 1.0}
    assert report["classes"]["novest"]["fp"] == 1
    assert report["classes"]["novest"]["recall"] is None
    assert report["classes"]["boots"]["precision"] is None
    assert report["by_condition"]["day"]["helmet"]["tp"] == 1
    assert report["by_condition"]["dim"]["helmet"]["fp"] == 1
    assert report["frame_count"] == 2 and report["session_count"] == 2 and report["camera_count"] == 1
    assert "helmet" not in report["unobserved_classes"] and "novest" in report["unobserved_classes"]
    assert report["frames"][1]["classes"]["helmet"]["fp"] == 1
    assert report["production_approved"] is False and report["label_quality_verified"] is False
    assert report["temporal_alert_pipeline_validated"] is False and report["frames_uploaded"] is False
    assert str(tmp_path) not in json.dumps(report)
    assert detector.detect.call_args.args[1] == 0.5
    detector.detect.side_effect = [[prediction("novest")], []]
    missed = evaluator.evaluate(path)
    assert missed["classes"]["helmet"]["fn"] == 1
    assert missed["classes"]["helmet"]["recall"] == 0


@pytest.mark.parametrize("case", ["class_order", "missing_label", "duplicate_bytes", "corrupt_image", "bad_label", "path_escape"])
def test_bad_dataset_never_produces_metrics(tmp_path, monkeypatch, case):
    path, manifest = dataset(tmp_path)
    monkeypatch.setattr(evaluator, "TrialDetector", lambda: Mock(detect=Mock(return_value=[])))
    if case == "class_order":
        manifest["classes"] = list(reversed(NAMES))
    elif case == "missing_label":
        (tmp_path / "frame-0.txt").unlink()
    elif case == "duplicate_bytes":
        (tmp_path / "frame-1.png").write_bytes((tmp_path / "frame-0.png").read_bytes())
    elif case == "corrupt_image":
        (tmp_path / "frame-0.png").write_bytes(b"not an image")
    elif case == "bad_label":
        (tmp_path / "frame-0.txt").write_text("6 0.5 0.5 1 1")
    else:
        manifest["frames"][0]["image"] = "../outside.png"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        evaluator.evaluate(path)


@pytest.mark.parametrize("confidence,iou", [(0, 0.5), (float("nan"), 0.5), (0.5, 0), (0.5, 1.1)])
def test_bad_thresholds_fail_before_model_load(tmp_path, monkeypatch, confidence, iou):
    model = Mock()
    monkeypatch.setattr(evaluator, "TrialDetector", model)
    with pytest.raises(ValueError):
        evaluator.evaluate(tmp_path / "absent.json", confidence, iou)
    model.assert_not_called()


def test_dataset_hash_tracks_label_changes(tmp_path, monkeypatch):
    path, _ = dataset(tmp_path)
    monkeypatch.setattr(evaluator, "TrialDetector", lambda: Mock(detect=Mock(return_value=[])))
    before = evaluator.evaluate(path)
    (tmp_path / "frame-0.txt").write_text("")
    after = evaluator.evaluate(path)
    assert before["dataset_content_sha256"] != after["dataset_content_sha256"]
    assert before["manifest_sha256"] == after["manifest_sha256"]
    assert after["classes"]["helmet"]["recall"] is None


def test_cli_preserves_evidence_and_writes_no_report_on_failure(tmp_path, monkeypatch, capsys):
    path, _ = dataset(tmp_path)
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["evaluate", "--manifest", str(path), "--output", str(output)])
    monkeypatch.setattr(evaluator, "MODEL_PATH", path)
    evaluate = Mock(side_effect=ValueError("private-sentinel"))
    monkeypatch.setattr(evaluator, "evaluate", evaluate)
    with pytest.raises(SystemExit) as error:
        evaluator.main()
    assert error.value.code == 2 and not output.exists()
    assert "private-sentinel" not in capsys.readouterr().err
    output.write_text("original evidence")
    evaluate.reset_mock()
    with pytest.raises(SystemExit):
        evaluator.main()
    assert output.read_text() == "original evidence"
    evaluate.assert_not_called()


@pytest.mark.skipif(not os.environ.get("TEST_PPE_ONNX"), reason="Optional pinned ONNX report smoke")
def test_actual_model_report_on_synthetic_negative_frames(tmp_path, monkeypatch):
    from src.validation.ppe_trial import TrialDetector
    path, _ = dataset(tmp_path)
    (tmp_path / "frame-0.txt").write_text("")
    monkeypatch.setattr(evaluator, "TrialDetector", lambda: TrialDetector(Path(os.environ["TEST_PPE_ONNX"])))
    report = evaluator.evaluate(path)
    assert report["unobserved_classes"] == list(NAMES)
    assert all(row["tp"] == row["fp"] == row["fn"] == 0 for row in report["classes"].values())
    assert report["production_approved"] is False


def test_cli_writes_readable_metrics_and_leaves_images_untouched(tmp_path, monkeypatch, capsys):
    path, _ = dataset(tmp_path)
    output = tmp_path / "results" / "report.json"
    image_before = (tmp_path / "frame-0.png").read_bytes()
    monkeypatch.setattr("sys.argv", ["evaluate", "--manifest", str(path), "--output", str(output)])
    monkeypatch.setattr(evaluator, "MODEL_PATH", path)
    monkeypatch.setattr(evaluator, "TrialDetector", lambda: Mock(detect=Mock(return_value=[])))
    evaluator.main()
    report = json.loads(output.read_text())
    assert report["status"] == "frame_metrics_measured_not_approved"
    assert report["classes"]["helmet"]["fn"] == 1
    assert report["created_at"]
    printed = capsys.readouterr().out
    assert "helmet: TP=0 FP=0 FN=1 precision=unmeasured recall=0.0%" in printed
    assert (tmp_path / "frame-0.png").read_bytes() == image_before
