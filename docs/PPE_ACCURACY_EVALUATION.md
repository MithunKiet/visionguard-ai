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

## Start here when no labeled dataset exists

1. Define the pilot's required PPE classes and intended camera views. The bundled evaluator uses only the six-class trial model above; it does not certify a different production checkpoint.
2. Collect a small **debugging** set first to learn the annotation workflow. Include helmet present/absent and vest present/absent examples, ordinary clothing that could resemble PPE, empty scenes, multiple people and relevant lighting/viewing distances. Do not deliberately remove required PPE on an active factory floor; use a safe staged area or authorized existing examples. Webcam examples help debug labels but do not represent factory CCTV.
3. Keep training, threshold-tuning and final held-out camera/session groups separate. Avoid adjacent video frames spread across splits. Record camera/session/condition metadata during collection. No audio or continuous recording is needed for this frame evaluation.
4. Annotate with a local YOLO TXT tool using the exact class order above. Label all visible supported objects, not only helmets. Review a sample with a second reviewer and resolve the box conventions before labeling the rest. Record ambiguous/excluded examples outside the scored manifest. Do not copy the model's predictions into ground truth.
5. Build the manifest using the existing example. Run the dataset check below before inference. Collect missing class/condition coverage, then review labels. An empty label file is a deliberate all-class negative, not a placeholder for unlabeled images.
6. Agree on precision/recall targets, critical missed-violation cases and required independent site/session coverage **before** inspecting held-out predictions. There is no universal image count or passing threshold that establishes readiness; correlated frames and rare failures matter. Reserve a new held-out set if you tune the model using evaluation failures.
7. Run the existing evaluator and inspect TP/FP/FN per class and condition. Review failed frame indices against the manifest locally. Keep production approval pending until site-specific label review and temporal alert tests are complete.

### Check labels and coverage without model weights

After installing the existing webcam Python dependencies, run from the project folder:

```bat
evaluate-ppe-windows.cmd "validation-data\webcam-held-out\manifest.json" --check-dataset
```

This mode does not require the ONNX weights and does not perform inference. It reports per-class object counts, positive/negative frame counts, empty-label frames and camera/session/condition coverage. It rejects missing/corrupt images, missing or invalid labels, exact duplicate image bytes, repeated identical labels and incorrect class order. The scoring label parser also rejects repeated identical labels. Input files are never changed. The normal report location remains `validation-results/ppe-accuracy-*.json`, but its status is explicitly `dataset_checked_not_accuracy_measured` and `accuracy_validated=false`.

Class-negative means no annotation for that class; it does not establish that an annotator correctly labeled the image. Coverage warnings describe missing evidence and are not an acceptance gate. The checker cannot detect all near-duplicates, incorrect annotations, train/test leakage or misleading camera/condition names. It never claims accuracy or production approval even with no warnings. It reads one image at a time; use trusted local files and sufficient memory for the source image resolution. Reports include declared dataset/camera/session/condition identifiers and hashes, but no image paths, pixels or raw labels; review identifiers before sharing reports.

Developer equivalent from `ai-worker/`:

```sh
python -m src.validation.ppe_evaluate --manifest ../validation-data/webcam-held-out/manifest.json --check-dataset --output ../validation-results/dataset-check.json
```
