# Measure the webcam trial model against labeled images

First run [the local PPE preview](PPE_WEBCAM_TRIAL.md). This optional next stage measures false positives and missed objects against manually reviewed labels. It runs the **same pinned six-class ONNX model**, confidence threshold and preprocessing as the preview. Your laptop images remain local. Neither the preview's box counts nor a successful camera check measures accuracy.

## Prepare independent examples

Use new images from your actual camera, including different sessions, lighting, distances, angles and partial occlusions relevant to your intended use. Choose examples before inspecting model predictions; do not select only successful detections. Reserve them for evaluation rather than training or threshold tuning. A small laptop collection is a debugging set, not evidence of factory readiness.

The current camera check and PPE preview do not save images. You can deliberately take still photos with the Windows Camera application, then close Camera before using the preview again. Use safe indoor examples and people who agree to participate. Keep the originals private under `validation-data/webcam-held-out/images/`; do not commit them or upload them to an online annotation service as part of this workflow. No continuous recording or audio is required for this frame-level study.

Manually label images using a locally installed annotation tool that can export **YOLO detection TXT** (for example, LabelImg). Review every image independently of model predictions. Label every clearly visible object in the six supported classes, using this exact order:

| ID | Class | Annotation convention |
| --- | --- | --- |
| 0 | `boots` | Box around each visible safety boot; ordinary shoes are not boots. |
| 1 | `helmet` | Box around each visible safety helmet. |
| 2 | `nohelmet` | Box around a clearly visible head without a safety helmet. |
| 3 | `novest` | Box around a clearly visible torso without a safety vest. |
| 4 | `person` | Box around each visible person. |
| 5 | `vest` | Box around each visible safety vest. |

A person box may overlap a helmet, vest or absence box. Do not invent absence labels for an obscured head/torso. Agree on box extent and ambiguous cases with a reviewer before scoring, and document excluded/ambiguous examples. These operational conventions must be checked against the model publisher's training-label definitions; inconsistent box conventions can change IoU scores. This tool does not verify label quality or infer ground truth.

Each label line contains `class_id center_x center_y width height`, normalized to image width/height. For example, `1 0.5 0.25 0.2 0.2` labels a helmet centered halfway across and one-quarter down the image, with width/height of 20%. This is a format example, not a label to copy onto your photos. An empty TXT file explicitly means **no objects from any of the six classes** are visible; a person without PPE still needs person/absence labels. A missing label file is an error.

Copy `ai-worker/training/ppe_trial_manifest.example.json` to `validation-data/webcam-held-out/manifest.json`. Put labels in `validation-data/webcam-held-out/labels/`. Keep the `classes` order unchanged, replace the dataset/session identifiers, and list every image and label using paths relative to the manifest. Each frame needs `camera_id`, `session_id` and `condition`, such as `day-near-unobstructed` or `dim-side-view`. Paths must remain inside the manifest directory. Identical image bytes and reused label paths are rejected; near-duplicates and overlap with training data still require manual review.

## Run on Windows

Run `test-ppe-windows.cmd` once to install the dependencies and verified model. Then open Command Prompt in the extracted project folder:

```bat
evaluate-ppe-windows.cmd "validation-data\webcam-held-out\manifest.json"
```

The launcher prints per-class precision/recall and writes `validation-results/ppe-accuracy-*.json`. It does not open the camera, download images, send alerts or upload frames. Existing evidence is never overwritten. The model must already be installed and must pass checksum verification.

The equivalent developer CLI, from `ai-worker/`, is:

```bat
..\.venv-webcam\Scripts\python.exe -m src.validation.ppe_evaluate --manifest ..\validation-data\webcam-held-out\manifest.json --confidence 0.5 --iou 0.5 --output ..\validation-results\ppe-accuracy-manual.json
```

Thresholds must be above zero and at most one. Fix thresholds before the held-out evaluation; use a separate development set for tuning. This is fixed-threshold frame scoring, not mAP or an event-level evaluation.

## Read the report

- **TP:** correct-class prediction matched to one labeled box at the selected intersection-over-union (IoU) threshold. Matching is greedy by descending confidence within each class.
- **FP:** unmatched prediction, including duplicate boxes and predictions on negative images.
- **FN:** labeled object without a matched prediction. A wrong-class prediction can create both an FP and an FN.
- **Precision:** TP / (TP + FP). **Recall:** TP / (TP + FN). Undefined denominators produce `null`/`unmeasured`, never a perfect score.
- `by_condition` separates the declared conditions. `unobserved_classes` identifies missing ground-truth coverage. The `frames` entries use zero-based manifest indices and hashes to locate errors without including image paths or image data.
- Model, manifest and image/label-content hashes identify the evaluated inputs. Held-out status is user-declared; hashing cannot establish independence or label correctness.

Share the report and the collection/labeling method when ready. Even high scores on a small set do not establish deployment readiness. The report always retains `production_approved=false`, `label_quality_verified=false` and `temporal_alert_pipeline_validated=false`. Repeated frames are not independent samples, and inference timings are not capture-to-alert latency. Factory validation additionally needs site cameras, sufficiently varied labeled examples, event-level tests, agreed acceptance targets and a reviewed model/license choice. See [REAL_CAMERA_VALIDATION.md](REAL_CAMERA_VALIDATION.md).
