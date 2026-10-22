"""Synthetic data and mock training verify workflow safeguards, not PPE accuracy."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image
import pytest
import yaml

from training.prepare_dataset import NAMES, prepare
from training import train


def dataset(tmp_path):
    rows = []
    for camera in range(5):
        for session in range(2):
            index = camera * 2 + session
            image, label = f'{index}.png', f'{index}.txt'
            Image.new('RGB', (16, 16), (index, 0, 0)).save(tmp_path / image)
            (tmp_path / label).write_text('0 0.5 0.5 0.5 0.5\n')
            rows.append(dict(image=image, label=label, camera_id=str(camera), session_id=str(session)))
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'classes': NAMES, 'frames': rows}))
    return path


def test_camera_groups_are_disjoint_reproducible_and_all_frames_retained(tmp_path):
    manifest = dataset(tmp_path)
    report = prepare(manifest, tmp_path / 'prepared')
    again = prepare(manifest, tmp_path / 'again')
    assert report['frames'] == again['frames']
    assert sum(report['frame_counts'].values()) == 10
    groups = {}
    for row in report['frames']:
        groups.setdefault(row['camera_id'], set()).add(row['split'])
    assert all(len(values) == 1 for values in groups.values())
    assert set(row['split'] for row in report['frames']) == {'train', 'val', 'test'}
    config = yaml.safe_load((tmp_path / 'prepared/dataset.yaml').read_text())
    assert config['names'] == dict(enumerate(NAMES))
    assert config['test'] == 'images/test'
    with pytest.raises(ValueError, match='new directory'):
        prepare(manifest, tmp_path / 'prepared')


def test_session_mode_is_explicit_and_groups_camera_session_pairs(tmp_path):
    path = dataset(tmp_path)
    data = json.loads(path.read_text())
    for index, row in enumerate(data['frames']):
        row['camera_id'] = 'one-camera'
        row['session_id'] = str(index // 2)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='three distinct'):
        prepare(path, tmp_path / 'camera')
    report = prepare(path, tmp_path / 'session', group_by='session')
    groups = {}
    for row in report['frames']:
        groups.setdefault(row['session_id'], set()).add(row['split'])
    assert all(len(value) == 1 for value in groups.values())


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'invalid_label', 'duplicate_label', 'escape', 'classes', 'corrupt'])
def test_invalid_input_never_creates_output(tmp_path, case):
    path = dataset(tmp_path)
    data = json.loads(path.read_text())
    if case == 'missing':
        (tmp_path / '0.txt').unlink()
    elif case == 'duplicate':
        (tmp_path / '1.png').write_bytes((tmp_path / '0.png').read_bytes())
    elif case == 'invalid_label':
        (tmp_path / '0.txt').write_text('0 nan 0.5 1 1')
    elif case == 'duplicate_label':
        (tmp_path / '0.txt').write_text('0 0.5 0.5 1 1\n0 0.5 0.5 1 1')
    elif case == 'escape':
        data['frames'][0]['image'] = '../outside.png'
    elif case == 'classes':
        data['classes'].reverse()
    else:
        (tmp_path / '0.png').write_bytes(b'invalid image')
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        prepare(path, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def args_for(tmp_path):
    base = tmp_path / 'base.pt'
    base.write_bytes(b'trusted-test-placeholder')
    data = tmp_path / 'dataset.yaml'
    data.write_text(yaml.safe_dump({'names': NAMES, 'train': 'images/train', 'val': 'images/val', 'test': 'images/test'}))
    return SimpleNamespace(model=str(base), model_sha256=hashlib.sha256(base.read_bytes()).hexdigest(), data=str(data),
                           epochs=1, imgsz=640, batch=1, device='cpu', export_onnx=False)


def test_training_saves_new_candidates_and_validates_best_not_last_epoch(tmp_path, monkeypatch):
    monkeypatch.setattr(train, 'CANDIDATES', tmp_path / 'candidates')
    active = tmp_path / 'models/yolov8s-ppe.pt'
    active.parent.mkdir()
    active.write_bytes(b'active model')
    loaded, calls = [], []
    class FakeModel:
        names = dict(enumerate(NAMES))
        def __init__(self, path):
            self.path = path
            loaded.append(path)
        def train(self, **kwargs):
            calls.append(kwargs)
            best = Path(kwargs['project']) / kwargs['name'] / 'weights/best.pt'
            best.parent.mkdir(parents=True)
            best.write_bytes(b'candidate checkpoint')
            self.trainer = SimpleNamespace(best=best)
        def val(self, **kwargs):
            assert Path(self.path).name == 'best.pt'
            assert kwargs['split'] == 'val'
            return SimpleNamespace(box=SimpleNamespace(map50=0.5, map=0.3))
    args = args_for(tmp_path)
    first, report = train.train_candidate(args, FakeModel)
    second, _ = train.train_candidate(args, FakeModel)
    assert first != second and first.is_file() and second.is_file()
    assert active.read_bytes() == b'active model'
    assert all(call['exist_ok'] is False for call in calls)
    assert report['runtime_weights_updated'] is False and report['held_out_test_evaluated'] is False
    assert report['weights_sha256'] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert (first.parent.parent / 'candidate.json').is_file()
    assert str(first) in loaded


def test_training_rejects_untrusted_base_before_model_load(tmp_path):
    args = args_for(tmp_path)
    args.model_sha256 = '0' * 64
    factory = Mock()
    with pytest.raises(ValueError, match='SHA-256'):
        train.train_candidate(args, factory)
    factory.assert_not_called()


@pytest.mark.parametrize('val,test', [(0, 0.2), (0.8, 0.3), (float('nan'), 0.2), (0.2, float('inf'))])
def test_invalid_split_ratios_fail_without_output(tmp_path, val, test):
    path = dataset(tmp_path)
    with pytest.raises(ValueError):
        prepare(path, tmp_path / 'out', val_split=val, test_split=test)
    assert not (tmp_path / 'out').exists()


def test_training_rejects_wrong_dataset_classes_before_loading(tmp_path):
    args = args_for(tmp_path)
    Path(args.data).write_text(yaml.safe_dump({'names': ['person'], 'train': 'train', 'val': 'val'}))
    factory = Mock()
    with pytest.raises(ValueError, match='nine-class'):
        train.train_candidate(args, factory)
    factory.assert_not_called()


def test_stale_checkpoint_outside_new_run_is_not_promoted_or_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(train, 'CANDIDATES', tmp_path / 'candidates')
    args = args_for(tmp_path)
    stale = tmp_path / 'old-best.pt'
    stale.write_bytes(b'old model')
    model = Mock(trainer=SimpleNamespace(best=stale))
    with pytest.raises(ValueError, match='inside this candidate run'):
        train.train_candidate(args, Mock(return_value=model))
    assert not list((tmp_path / 'candidates').rglob('candidate.json'))
    assert stale.read_bytes() == b'old model'
