# PPE candidate training and grouped dataset preparation

Training produces a candidate, never a deployed model. Production requires trusted nine-class weights, reviewed SHA-256 and CUDA; missing weights fail startup. See [PPE_MODEL_SELECTION.md](PPE_MODEL_SELECTION.md) before choosing a base model or collecting data. No factory model has been trained or approved by the synthetic tests for these scripts.

## Prepare independent data

Collect authorized examples spanning intended cameras, lighting, distances, crowding and occlusions. Label visible positive and explicit absence classes using the exact production order:

| ID | Class |
| --- | --- |
| 0 | helmet |
| 1 | no_helmet |
| 2 | vest |
| 3 | no_vest |
| 4 | gloves |
| 5 | no_gloves |
| 6 | safety_shoes |
| 7 | no_safety_shoes |
| 8 | person |

YOLO TXT rows contain class ID and normalized center-x, center-y, width, height. Empty files explicitly declare no supported objects; missing files are errors. Do not manufacture glove/shoe labels to fit a helmet/vest-only dataset. Exact class names alone do not establish trained capability or annotation quality.

Copy `ai-worker/training/group_manifest.example.json` into an ignored directory such as `validation-data/training-source/manifest.json`. Replace its illustrative records with your images, labels, camera IDs and session IDs; paths must stay within the manifest directory. Install the worker's inference/training dependencies (including Pillow and PyYAML) in an isolated environment. From the repository root:

```sh
python ai-worker/training/prepare_dataset.py \
  --manifest validation-data/training-source/manifest.json \
  --out validation-data/prepared-ppe --group-by camera \
  --val-split 0.2 --test-split 0.2 --seed 42
```

Default camera grouping assigns all sessions of one camera to one partition. For a deliberately within-camera experiment, explicitly choose `--group-by session`; each `(camera_id, session_id)` pair stays together. That mode does not establish performance on unseen cameras. At least three groups and nonempty train/val/test partitions are required. Fractions apply to **group counts**, not image counts; rounding and a minimum one group per evaluation partition can change realized proportions. `split-report.json` records actual group/frame counts and per-frame assignments/hashes.

The new CLI replaces `--source`; old random per-image splitting is not retained as a fallback. Input checks reject malformed/corrupt images, missing/invalid labels, duplicate identical annotations, reused label paths, exact duplicate image bytes, incorrect class order and path escapes before creating output. Deterministic grouping depends on the same inputs and seed. These checks do not find all near-duplicates, cross-camera views of the same event, incorrect metadata, annotation errors or missing class coverage. Review those separately and keep related events in a single group when collecting data.

Output must be a new directory. The tool does not merge or overwrite datasets. It produces `images/{train,val,test}`, corresponding labels, `dataset.yaml` and a completion `split-report.json`. Numeric destination names avoid source-basename collisions. Copied contents are checked against the pre-copy hashes. An I/O failure may leave incomplete output; without a valid completion report, discard that directory and rerun to a new destination. Keep all private images and reports outside source control.

## Train a candidate

Use a trusted local base `.pt` and independently reviewed SHA-256. A hash of an unknown download is not trust or commercial-use approval. The CLI no longer downloads a default base model implicitly:

```sh
python ai-worker/training/train.py \
  --model /local/trusted/yolov8s.pt --model-sha256 EXPECTED_SHA256 \
  --data validation-data/prepared-ppe/dataset.yaml \
  --epochs 100 --imgsz 640 --batch 4 --device 0
```

Batch size 4 is only an example, not a claim that a particular GPU can train this workload. Choose it from available memory and monitor training. The owner-reported CUDA smoke does not measure training or inference capacity.

Each run receives a unique directory under ignored `ai-worker/training/candidates/ppe-<uuid>/`. Training validates the supplied dataset class order and checkpoint hash, then evaluates the saved `weights/best.pt` on **val**, not the final in-memory epoch. `candidate.json` records base/candidate hashes, dataset YAML hash, requested training parameters and development mAP. A YAML hash does not fingerprint the underlying images; retain the preparation report and immutable source dataset alongside the candidate. Failed runs can leave partial artifacts and are not completed candidates.

Optional `--export-onnx` exports next to candidate weights; it does not install that export into the runtime. `production_approved=false`, `runtime_weights_updated=false` and `held_out_test_evaluated=false` remain explicit. No active model is replaced, no worker restart is triggered and no model-updated event is sent. Use an isolated training environment; this workflow does not add a training process timeout or resource scheduler.

## Review and separately deploy

Keep the test split sealed through model selection and threshold tuning. Before a separate, deliberate deployment:

1. Review model/data licensing, label conventions and class/condition coverage.
2. Measure independent factory per-class precision/recall and errors using [REAL_CAMERA_VALIDATION.md](REAL_CAMERA_VALIDATION.md); do not report development mAP as held-out acceptance. Adapt the held-out test files into that evaluator's manifest with retained camera/session/condition metadata.
3. Run [MODEL_READINESS.md](MODEL_READINESS.md) and [WINDOWS_GPU.md](WINDOWS_GPU.md) or the deployment-hardware benchmark with the candidate hash.
4. Complete the [factory pilot acceptance](FACTORY_PILOT_ACCEPTANCE.md), retaining previous weights/hash and a rollback plan before changing runtime settings.

No universal image count, mAP threshold or fixed camera distance proves production suitability. Set per-class/condition targets and sampling requirements before inspecting held-out results. A five-class helmet/vest model still requires a supported-class contract change before it can replace the current nine-class production detector.
