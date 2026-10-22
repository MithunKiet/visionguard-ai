"""Verify explicit public-dataset class mapping and exploratory report boundaries."""
import json
from unittest.mock import Mock

from PIL import Image
import pytest
import yaml

from src.validation.public_ppe import SOURCE_CLASSES, evaluate


def fixture(tmp_path):
    for split in ['train', 'val', 'test']:
        (tmp_path / 'images' / split).mkdir(parents=True)
        (tmp_path / 'labels' / split).mkdir(parents=True)
    (tmp_path / 'data.yaml').write_text(yaml.safe_dump({'names': dict(enumerate(SOURCE_CLASSES))}))
    Image.new('RGB', (100, 100), 'red').save(tmp_path / 'images/test/a.png')
    (tmp_path / 'labels/test/a.txt').write_text('0 0.5 0.5 1 1\n2 0.5 0.5 1 1\n')
    return tmp_path


def test_source_helmet_and_vest_ids_are_scored_not_trial_ids(tmp_path):
    root = fixture(tmp_path)
    model = Mock(detect=Mock(return_value=[{'class_name': 'helmet', 'bbox': [0, 0, 100, 100], 'confidence': 0.9},
                                        {'class_name': 'novest', 'bbox': [0, 0, 100, 100], 'confidence': 0.9}]))
    report = evaluate(root, detector=model)
    assert report['metrics']['all_valid_test']['helmet']['tp'] == 1
    assert report['metrics']['all_valid_test']['vest']['fn'] == 1
    assert report['metrics']['all_valid_test']['vest']['precision'] is None
    assert report['evaluated_frames'] == report['byte_disjoint_frames'] == 1
    assert not report['production_approved'] and not report['training_performed']
    assert not report['missing_vest_accuracy_measured'] and not report['pretraining_overlap_known']
    assert str(tmp_path) not in json.dumps(report)


def test_exact_reference_overlap_is_reported_and_excluded_from_filtered_metrics(tmp_path):
    root = fixture(tmp_path)
    (root / 'images/train/copy.png').write_bytes((root / 'images/test/a.png').read_bytes())
    report = evaluate(root, detector=Mock(detect=Mock(return_value=[])))
    assert report['evaluated_frames'] == 1 and report['byte_disjoint_frames'] == 0
    assert report['frames'][0]['byte_overlap_train_or_val']
    assert report['metrics']['all_valid_test']['vest']['fn'] == 1
    assert report['metrics']['byte_disjoint_test']['vest']['recall'] is None


def test_rejected_annotation_is_visible_and_never_inferred(tmp_path):
    root = fixture(tmp_path)
    (root / 'labels/test/a.txt').unlink()
    model = Mock()
    report = evaluate(root, detector=model)
    assert report['evaluated_frames'] == 0
    assert len(report['rejected_inputs']) == 1
    model.detect.assert_not_called()


def test_wrong_class_contract_is_rejected_before_model_loading(tmp_path):
    root = fixture(tmp_path)
    (root / 'data.yaml').write_text(yaml.safe_dump({'names': list(reversed(SOURCE_CLASSES))}))
    with pytest.raises(ValueError, match='class mapping'):
        evaluate(root)
