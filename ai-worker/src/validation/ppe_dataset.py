"""Check local trial-model evaluation data without loading weights or running inference."""
import hashlib
from pathlib import Path

import cv2
import numpy as np

from src.validation.camera import load_manifest, local_file
from src.validation.metrics import read_yolo_labels
from src.validation.ppe_trial import NAMES


def inspect_dataset(manifest_path):
    path = Path(manifest_path)
    manifest = load_manifest(path)
    if manifest.get('classes') != list(NAMES):
        raise ValueError('Manifest class order must match the six-class trial model')
    root = path.resolve().parent
    counts = {name: {'objects': 0, 'positive_frames': 0, 'negative_frames': 0} for name in NAMES}
    groups = {key: {} for key in ('camera_id', 'session', 'condition')}
    seen, frames = set(), []
    digest = hashlib.sha256()
    empty = 0
    for index, row in enumerate(manifest['frames']):
        image_bytes = local_file(root, row['image']).read_bytes()
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        if image_hash in seen:
            raise ValueError('Duplicate image content would inflate evaluation')
        seen.add(image_hash)
        frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('A labeled image cannot be decoded')
        label_path = local_file(root, row['label'])
        truth = read_yolo_labels(label_path, frame.shape[1], frame.shape[0], NAMES)
        boxes = [(item['class_name'], tuple(item['bbox'])) for item in truth]
        if len(boxes) != len(set(boxes)):
            raise ValueError('Repeated identical labels would inflate support')
        label_hash = hashlib.sha256(label_path.read_bytes()).hexdigest()
        digest.update(bytes.fromhex(image_hash))
        digest.update(bytes.fromhex(label_hash))
        empty += not truth
        for name in NAMES:
            support = sum(item['class_name'] == name for item in truth)
            counts[name]['objects'] += support
            counts[name]['positive_frames'] += support > 0
            counts[name]['negative_frames'] += support == 0
        for key, value in [('camera_id', row['camera_id']), ('session', (row['camera_id'], row['session_id'])), ('condition', row['condition'])]:
            groups[key][value] = groups[key].get(value, 0) + 1
        frames.append({'frame_index': index, 'image_sha256': image_hash, 'label_sha256': label_hash,
                       'width': frame.shape[1], 'height': frame.shape[0], 'labeled_objects': len(truth)})
    warnings = []
    for name, values in counts.items():
        if not values['positive_frames']:
            warnings.append(f'{name}: no labeled positive frames; recall cannot be measured')
        if not values['negative_frames']:
            warnings.append(f'{name}: no labeled negative frames; negative-scene behavior is untested')
    if len(groups['camera_id']) < 2:
        warnings.append('Only one camera represented; results cannot establish cross-camera behavior')
    if len(groups['session']) < 2:
        warnings.append('Only one camera/session represented; collect independent sessions')
    if len(groups['condition']) < 2:
        warnings.append('Only one declared condition represented; collect intended lighting and viewing conditions')
    return {'status': 'dataset_checked_not_accuracy_measured', 'dataset_id': manifest['dataset_id'],
            'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'dataset_content_sha256': digest.hexdigest(),
            'frame_count': len(frames), 'empty_label_frames': empty, 'classes': counts,
            'camera_count': len(groups['camera_id']), 'session_count': len(groups['session']),
            'by_camera': groups['camera_id'], 'by_condition': groups['condition'],
            'by_session': [{'camera_id': key[0], 'session_id': key[1], 'frames': count} for key, count in groups['session'].items()],
            'frames': frames, 'coverage_warnings': warnings,
            'label_quality_verified': False, 'held_out_status': 'user_declared_not_independently_verified',
            'accuracy_validated': False, 'production_approved': False, 'inference_run': False,
            'frames_uploaded': False, 'operational_alerts_sent': False}
