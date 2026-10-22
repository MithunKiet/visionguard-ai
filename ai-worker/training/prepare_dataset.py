"""Prepare a new YOLO dataset with disjoint camera or camera/session groups."""
import argparse
import hashlib
import json
import math
import random
import shutil
from pathlib import Path

NAMES = ['helmet', 'no_helmet', 'vest', 'no_vest', 'gloves', 'no_gloves', 'safety_shoes', 'no_safety_shoes', 'person']


def local_file(root, name):
    if not isinstance(name, str) or not name:
        raise ValueError('Each image and label needs a relative file path')
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Input files must exist inside the manifest directory')
    return path


def prepare(manifest_path, out, group_by='camera', val_split=0.2, test_split=0.2, seed=42):
    if group_by not in {'camera', 'session'} or not (0 < val_split < 1 and 0 < test_split < 1 and val_split + test_split < 1):
        raise ValueError('Choose valid grouping and positive train/val/test proportions')
    manifest_path, out = Path(manifest_path).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('Output must be a new directory; existing datasets are never merged')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest.get('classes') != NAMES or not isinstance(manifest.get('frames'), list) or not manifest['frames']:
        raise ValueError('Supply nonempty frames and the exact production class order')
    root = manifest_path.parent
    groups, records, seen_images, seen_labels = {}, [], set(), set()
    for index, row in enumerate(manifest['frames']):
        if not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key].strip() for key in ('camera_id', 'session_id')):
            raise ValueError('Each frame requires camera_id and session_id')
        image, label = local_file(root, row.get('image')), local_file(root, row.get('label'))
        if image.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.bmp'} or label.suffix.lower() != '.txt':
            raise ValueError('Use supported image files and YOLO TXT labels')
        image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
        if image_hash in seen_images or label in seen_labels:
            raise ValueError('Duplicate image content or reused label file')
        seen_images.add(image_hash)
        seen_labels.add(label)
        from PIL import Image
        with Image.open(image) as decoded:
            decoded.load()
        seen_boxes = set()
        for line in label.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError('Labels require class ID and four normalized coordinates')
            cls = int(parts[0])
            x, y, w, h = map(float, parts[1:])
            if (not 0 <= cls < len(NAMES) or not all(math.isfinite(v) for v in (x, y, w, h))
                    or not 0 < w <= 1 or not 0 < h <= 1 or min(x-w/2, y-h/2) < -1e-6 or max(x+w/2, y+h/2) > 1+1e-6):
                raise ValueError('Invalid normalized label')
            box = (cls, x, y, w, h)
            if box in seen_boxes:
                raise ValueError('Repeated identical label')
            seen_boxes.add(box)
        key = (row['camera_id'],) if group_by == 'camera' else (row['camera_id'], row['session_id'])
        record = {'frame_index': index, 'camera_id': row['camera_id'], 'session_id': row['session_id'],
                  'image_sha256': image_hash, 'label_sha256': hashlib.sha256(label.read_bytes()).hexdigest()}
        groups.setdefault(key, []).append((image, label, record))
    keys = sorted(groups)
    if len(keys) < 3:
        raise ValueError('At least three distinct groups are required for train, val and held-out test')
    random.Random(seed).shuffle(keys)
    n_test, n_val = max(1, round(len(keys) * test_split)), max(1, round(len(keys) * val_split))
    if n_test + n_val >= len(keys):
        raise ValueError('Requested proportions leave no training group; add groups or reduce fractions')
    splits = {'test': keys[:n_test], 'val': keys[n_test:n_test+n_val], 'train': keys[n_test+n_val:]}
    out.mkdir(parents=True, exist_ok=False)
    # Completion report is written last; partial outputs after I/O failure must be discarded, never reused.
    for split, group_keys in splits.items():
        (out / 'images' / split).mkdir(parents=True)
        (out / 'labels' / split).mkdir(parents=True)
        for key in group_keys:
            for image, label, record in groups[key]:
                stem = f"{record['frame_index']:08d}"
                image_dest = out / 'images' / split / (stem + image.suffix.lower())
                label_dest = out / 'labels' / split / (stem + '.txt')
                shutil.copyfile(image, image_dest)
                shutil.copyfile(label, label_dest)
                if (hashlib.sha256(image_dest.read_bytes()).hexdigest() != record['image_sha256']
                        or hashlib.sha256(label_dest.read_bytes()).hexdigest() != record['label_sha256']):
                    raise ValueError('Input content changed during preparation')
                records.append({**record, 'split': split, 'image': str(image_dest.relative_to(out)), 'label': str(label_dest.relative_to(out))})
    # JSON quoted strings are valid YAML scalars, including Windows paths.
    config = 'path: ' + json.dumps(str(out)) + '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n'
    config += ''.join(f'  {i}: {name}\n' for i, name in enumerate(NAMES))
    (out / 'dataset.yaml').write_text(config, encoding='utf-8')
    report = {'status': 'dataset_prepared_not_validated', 'group_by': group_by, 'seed': seed,
              'requested_group_fractions': {'val': val_split, 'test': test_split},
              'group_counts': {split: len(values) for split, values in splits.items()},
              'frame_counts': {split: sum(row['split'] == split for row in records) for split in splits},
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'production_approved': False, 'label_quality_verified': False, 'frames': records}
    (out / 'split-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--group-by', choices=['camera', 'session'], default='camera')
    parser.add_argument('--val-split', type=float, default=0.2)
    parser.add_argument('--test-split', type=float, default=0.2)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    try:
        report = prepare(args.manifest, args.out, args.group_by, args.val_split, args.test_split, args.seed)
        print('Dataset prepared; keep test split sealed during training and tuning.')
        print(json.dumps(report['frame_counts']))
    except Exception as error:
        print(f'Preparation failed ({type(error).__name__}); check groups, paths, labels and new output directory.')
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
