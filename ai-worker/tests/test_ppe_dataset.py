"""Synthetic fixtures verify data checks, never real PPE accuracy."""
import json
from unittest.mock import Mock

import pytest
from tests.test_ppe_evaluate import dataset
from src.validation import ppe_evaluate
from src.validation.ppe_dataset import inspect_dataset


def test_coverage_counts_negatives_and_missing_classes_without_inference(tmp_path, monkeypatch):
    path, _ = dataset(tmp_path)
    detector = Mock(side_effect=AssertionError('No inference allowed'))
    monkeypatch.setattr(ppe_evaluate, 'TrialDetector', detector)
    report = inspect_dataset(path)
    assert report['classes']['helmet'] == {'objects': 1, 'positive_frames': 1, 'negative_frames': 1}
    assert report['classes']['vest'] == {'objects': 0, 'positive_frames': 0, 'negative_frames': 2}
    assert report['empty_label_frames'] == 1
    assert report['session_count'] == 2 and report['camera_count'] == 1
    assert report['by_condition'] == {'day': 1, 'dim': 1}
    assert any('vest: no labeled positive' in warning for warning in report['coverage_warnings'])
    assert not report['accuracy_validated'] and not report['production_approved']
    assert not report['inference_run'] and not report['label_quality_verified']
    assert str(tmp_path) not in json.dumps(report)
    detector.assert_not_called()


@pytest.mark.parametrize('case', ['duplicate_image', 'duplicate_label', 'missing_label', 'corrupt_image', 'wrong_classes'])
def test_invalid_data_rejected(tmp_path, case):
    path, manifest = dataset(tmp_path)
    if case == 'duplicate_image':
        (tmp_path / 'frame-1.png').write_bytes((tmp_path / 'frame-0.png').read_bytes())
    elif case == 'duplicate_label':
        (tmp_path / 'frame-0.txt').write_text('1 0.5 0.5 1 1\n1 0.5 0.5 1 1\n')
    elif case == 'missing_label':
        (tmp_path / 'frame-0.txt').unlink()
    elif case == 'corrupt_image':
        (tmp_path / 'frame-0.png').write_bytes(b'invalid')
    else:
        manifest['classes'] = list(reversed(manifest['classes']))
        path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        inspect_dataset(path)


def test_cli_check_works_without_weights_preserves_inputs_and_report(tmp_path, monkeypatch, capsys):
    path, _ = dataset(tmp_path)
    output = tmp_path / 'coverage.json'
    monkeypatch.setattr(ppe_evaluate, 'MODEL_PATH', tmp_path / 'absent-model.onnx')
    detector = Mock(side_effect=AssertionError('No inference allowed'))
    monkeypatch.setattr(ppe_evaluate, 'TrialDetector', detector)
    before = (tmp_path / 'frame-0.png').read_bytes()
    monkeypatch.setattr('sys.argv', ['evaluate', '--manifest', str(path), '--check-dataset', '--output', str(output)])
    ppe_evaluate.main()
    report = json.loads(output.read_text())
    assert report['status'] == 'dataset_checked_not_accuracy_measured'
    assert 'Accuracy has not been measured' in capsys.readouterr().out
    assert (tmp_path / 'frame-0.png').read_bytes() == before
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        ppe_evaluate.main()
    assert output.read_bytes() == original
    detector.assert_not_called()
