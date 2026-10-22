"""Train a new PPE candidate; never replace runtime weights or approve deployment."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import yaml

if __package__:
    from .prepare_dataset import NAMES
else:
    from prepare_dataset import NAMES

CANDIDATES = Path(__file__).resolve().parent / 'candidates'


def train_candidate(args, model_factory=None):
    base, data = Path(args.model).resolve(), Path(args.data).resolve()
    if not base.is_file() or base.suffix.lower() != '.pt' or not data.is_file():
        raise ValueError('Supply trusted local .pt base weights and a dataset YAML')
    base_hash = hashlib.sha256(base.read_bytes()).hexdigest()
    if base_hash != args.model_sha256.lower():
        raise ValueError('Base weights differ from reviewed SHA-256')
    config = yaml.safe_load(data.read_text(encoding='utf-8-sig'))
    names = config.get('names') if isinstance(config, dict) else None
    if names != NAMES and names != dict(enumerate(NAMES)):
        raise ValueError('Dataset must use the exact nine-class production mapping')
    if not config.get('train') or not config.get('val'):
        raise ValueError('Separate training and development splits are required')
    if any(value <= 0 for value in (args.epochs, args.imgsz, args.batch)):
        raise ValueError('Epochs, image size and batch must be positive')
    run_id = 'ppe-' + uuid4().hex
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    requested = CANDIDATES / run_id
    if model_factory is None:
        from ultralytics import YOLO
        model_factory = YOLO
    model = model_factory(str(base))
    model.train(data=str(data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=args.device,
                project=str(CANDIDATES), name=run_id, exist_ok=False, hsv_v=0.5, degrees=5.0)
    best = Path(model.trainer.best).resolve()
    if not best.is_file() or not best.is_relative_to(requested.resolve()):
        raise ValueError('Trainer did not produce a checkpoint inside this candidate run')
    candidate = model_factory(str(best))
    if candidate.names != dict(enumerate(NAMES)):
        raise ValueError('Candidate class mapping does not match production')
    # Score the saved best checkpoint, not the last in-memory training epoch.
    metrics = candidate.val(data=str(data), split='val', device=args.device)
    exported = False
    if args.export_onnx:
        candidate.export(format='onnx', imgsz=args.imgsz)
        exported = True
    report = {'status': 'candidate_trained_not_approved', 'created_at': datetime.now(timezone.utc).isoformat(),
              'candidate_id': run_id, 'base_sha256': base_hash,
              'weights_sha256': hashlib.sha256(best.read_bytes()).hexdigest(),
              'dataset_yaml_sha256': hashlib.sha256(data.read_bytes()).hexdigest(),
              'classes': NAMES, 'epochs_requested': args.epochs, 'image_size': args.imgsz,
              'batch_size': args.batch, 'device_requested': args.device,
              'development_metrics': {'map50': float(metrics.box.map50), 'map50_95': float(metrics.box.map)},
              'held_out_test_evaluated': False, 'production_approved': False, 'runtime_weights_updated': False,
              'onnx_exported': exported}
    serialized = json.dumps(report, indent=2, allow_nan=False)
    with (requested / 'candidate.json').open('x', encoding='utf-8') as file:
        file.write(serialized)
    return best, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='Trusted local base .pt checkpoint')
    parser.add_argument('--model-sha256', required=True, help='Independently reviewed base checkpoint SHA-256')
    parser.add_argument('--data', required=True, help='Dataset YAML with separate train/val/test groups')
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--device', default='0')
    parser.add_argument('--export-onnx', action='store_true')
    args = parser.parse_args()
    try:
        best, report = train_candidate(args)
        print(f'Candidate checkpoint: {best}')
        print(f"Development mAP@50: {report['development_metrics']['map50']:.3f}")
        print('Runtime model unchanged. Review candidate.json, held-out accuracy and capacity before separate deployment.')
    except Exception as error:
        print(f'Training incomplete ({type(error).__name__}); no candidate approval or runtime promotion performed.')
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
