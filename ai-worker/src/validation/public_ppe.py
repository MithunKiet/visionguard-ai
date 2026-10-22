"""Exploratory helmet/vest scoring on local Construction-PPE test data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np
import yaml

from src.validation.metrics import read_yolo_labels, score_frame, summarize
from src.validation.ppe_trial import MODEL_SHA256, TrialDetector

SOURCE_URL = 'https://github.com/ultralytics/assets/releases/download/v0.0.0/construction-ppe.zip'
SOURCE_SHA256 = 'bef8dcb599aa4e9d9f5e602cb6fa7143d3c84d7f6a0ff40463d7f2a4c2632ccc'
SOURCE_CLASSES = ['helmet', 'gloves', 'vest', 'boots', 'goggles', 'none', 'Person', 'no_helmet', 'no_goggle', 'no_gloves', 'no_boots']
SCORED_CLASSES = ['helmet', 'vest']


def image_files(root, split):
    return sorted(p for p in (root / 'images' / split).iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp'})


def evaluate(root, confidence=0.5, iou=0.5, detector=None):
    root = Path(root)
    if not 0 < confidence <= 1 or not 0 < iou <= 1:
        raise ValueError('Invalid thresholds')
    names = yaml.safe_load((root / 'data.yaml').read_text())['names']
    if names != dict(enumerate(SOURCE_CLASSES)) and names != SOURCE_CLASSES:
        raise ValueError('Unexpected source class mapping')
    reference_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for split in ['train', 'val'] for p in image_files(root, split)}
    test = image_files(root, 'test')
    if not test:
        raise ValueError('No test images')
    detector = detector or TrialDetector()
    totals = {key: {name: {'tp': 0, 'fp': 0, 'fn': 0} for name in SCORED_CLASSES} for key in ['all_valid_test', 'byte_disjoint_test']}
    frames, rejected, seen = [], [], set()
    for index, path in enumerate(test):
        image_bytes = path.read_bytes()
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        repeated = image_hash in seen
        seen.add(image_hash)
        label_path = root / 'labels' / 'test' / (path.stem + '.txt')
        try:
            frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError('Image decode failed')
            truth = read_yolo_labels(label_path, frame.shape[1], frame.shape[0], SOURCE_CLASSES)
        except (ValueError, OSError) as error:
            rejected.append({'frame_index': index, 'image_sha256': image_hash, 'reason': type(error).__name__})
            continue
        started = time.perf_counter()
        predictions = detector.detect(frame, confidence)
        elapsed = (time.perf_counter() - started) * 1000
        truth = [row for row in truth if row['class_name'] in SCORED_CLASSES]
        predictions = [row for row in predictions if row['class_name'] in SCORED_CLASSES]
        counts = score_frame(truth, predictions, SCORED_CLASSES, confidence, iou)
        disjoint = image_hash not in reference_hashes and not repeated
        for key in ['all_valid_test'] + (['byte_disjoint_test'] if disjoint else []):
            for name in SCORED_CLASSES:
                for metric, count in counts[name].items():
                    totals[key][name][metric] += count
        frames.append({'frame_index': index, 'image_sha256': image_hash,
                       'label_sha256': hashlib.sha256(label_path.read_bytes()).hexdigest(), 'classes': counts,
                       'byte_overlap_train_or_val': image_hash in reference_hashes,
                       'repeated_test_bytes': repeated, 'byte_disjoint': disjoint, 'inference_ms': elapsed})
        if (index + 1) % 20 == 0:
            print(f'Evaluated source test entry {index + 1}/{len(test)}', flush=True)
    return {'status': 'public_dataset_exploration_not_approved', 'created_at': datetime.now(timezone.utc).isoformat(),
            'dataset': 'Ultralytics Construction-PPE', 'source_url': SOURCE_URL,
            'reference_archive_sha256': SOURCE_SHA256,
            'source_yaml_sha256': hashlib.sha256((root / 'data.yaml').read_bytes()).hexdigest(),
            'model_sha256': MODEL_SHA256, 'model_kind': 'six_class_webcam_trial', 'device': 'cpu',
            'confidence_threshold': confidence, 'iou_threshold': iou, 'scored_classes': SCORED_CLASSES,
            'source_test_frames': len(test), 'evaluated_frames': len(frames), 'rejected_inputs': rejected,
            'byte_disjoint_frames': sum(row['byte_disjoint'] for row in frames),
            'metrics': {key: summarize(counts) for key, counts in totals.items()}, 'frames': frames,
            'training_performed': False, 'production_approved': False, 'label_quality_verified': False,
            'pretraining_overlap_known': False, 'near_duplicate_independence_verified': False,
            'missing_vest_accuracy_measured': False, 'temporal_alert_pipeline_validated': False,
            'note': 'Positive helmet/vest object scoring only. Public labels are not independently reviewed; exact byte filtering does not prove held-out independence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new report path')
    report = evaluate(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as file:
        json.dump(report, file, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in ['source_test_frames', 'evaluated_frames', 'byte_disjoint_frames', 'metrics']}, indent=2))


if __name__ == '__main__':
    main()
