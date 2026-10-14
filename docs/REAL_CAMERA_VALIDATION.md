# Validate detection on real cameras

The validation runner is read-only: it does not publish events, create alerts, notify staff, write to application databases or deploy model weights. Stream quality and detection accuracy are separate measurements. A successful probe is not evidence of accurate PPE detection, and frame scores do not validate the temporal alert pipeline.

## Required inputs

- An authorized RTSP camera reachable from the validation machine. Store the full URL in an environment variable such as `VALIDATION_RTSP_URL`, including credentials if required. Do not put passwords in commands, Git, reports or chat. The cloud environment will need a permitted network route to the camera; a private factory address is not automatically reachable from the cloud.
- A trusted local PPE checkpoint compatible with the runtime class mapping below. Do not use generic COCO weights or synthetic demo detections. Local evaluation disables remote inference, so footage is not uploaded to a model provider. Install the AI worker's pinned dependencies on the target validation machine before inference; lightweight probe/tests only need OpenCV and the test dependencies.
- Independently reviewed held-out frames, YOLO label files and a manifest. Keep tuning/training footage separate by recording session/person/shift as appropriate; randomly splitting adjacent frames from one clip does not establish a held-out camera evaluation. The tool checks the declaration, not the truth of the dataset's provenance or independence.
- Site-approved target metrics, representative lighting/occlusion/distances, a reviewer and the actual deployment hardware for capacity measurements. A cloud CPU run cannot establish GPU or factory-network capacity.

Keep inputs under the gitignored `validation-data/` directory and outputs under `validation-results/`. They can contain sensitive site metadata. Use controlled storage/retention and avoid committing footage, labels, weights or actual camera reports.

## 1. Probe the camera without recording

From `ai-worker/`, using its prepared Python environment:

```sh
python -m src.validation.camera probe \
  --url-env VALIDATION_RTSP_URL --seconds 30 \
  --output ../validation-results/camera-01-probe.json
```

The URL comes from the named environment variable, not a CLI argument. The decoder runs in a child process with native stderr suppressed, 10-second open/read timeouts and a parent deadline of probe duration plus 25 seconds. A stuck native decoder is terminated. Unreachable/incomplete/timed-out streams exit nonzero; choose a new output path for every run to preserve evidence.

The JSON report contains decoded frame count, dimensions, camera-reported FPS, measured decode throughput, maximum interframe gap and average image luminance. It contains no camera URL and saves no images or audio. The built-in recommended installation profile is at least 1920×1080 at 15 FPS, but resolution/FPS alone cannot establish the observable PPE area or accuracy.

Decode throughput can exceed reported camera FPS while an initial buffered backlog drains. It is **not** capture-to-display latency or proof of fresh frames. Luminance is an image statistic, not a lux measurement. Measure camera timestamps/clock synchronization, field of view, PPE pixel sizes, light level, blur and occlusion separately. Record physical distances at marked observation points; do not infer one universal detection distance.

## 2. Score labeled frames through the runtime detector

Use the JSON layout in `ai-worker/training/validation_manifest.example.json`. Paths must be relative to and contained inside the manifest's directory. Every image requires an explicit label file; a truly negative frame has an empty file. Missing labels, duplicate entries, unsafe paths and invalid boxes fail the run instead of being treated as clean observations.

The label file format is one object per line: `class_id center_x center_y width height`, normalized to image dimensions. The class order matches `PPE_CLASSES` in `src/pipeline/detector.py`:

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

Label visible objects and violation regions consistently with the model's training convention. Exclude unscorable/ambiguous frames before freezing the dataset, record exclusions and use independent review. Do not silently label an obscured body part as missing PPE. This local model contract does not include masks, violence or named-person identification.

```sh
python -m src.validation.camera evaluate \
  --manifest ../validation-data/site-a/manifest.json \
  --weights models/yolov8s-ppe.pt \
  --confidence 0.6 --iou 0.5 --device cpu \
  --output ../validation-results/site-a-held-out.json
```

Use `--device cuda` on the intended GPU host; the report records the actual device because the existing detector falls back to CPU when CUDA is unavailable. Missing checkpoints/dependencies, incompatible class mappings or inference errors fail the run. No checkpoint is downloaded or promoted by this runner. Keep the dataset and checkpoint immutable while evaluating.

The evaluation uses `PPEDetector.detect`, including runtime CLAHE preprocessing and its existing YOLO inference/NMS defaults. It matches boxes per class, highest confidence first, with one-to-one IoU matching; duplicate predictions count as false positives. Results include TP/FP/FN, precision, recall and label support per class and condition, plus model/manifest/dataset-content SHA-256 hashes, camera/session/frame counts and inference p50/p95. Classes with no ground-truth examples are listed as unobserved, and undefined precision/recall is null. The configurable scoring confidence filters the detector's emitted candidates; it cannot restore candidates already removed by the detector's own confidence/NMS defaults.

These are frame-object metrics at one confidence/IoU setting, **not mAP**, event recall, false alerts per camera-hour or calibrated probability. Inference timings include the first cold call and exclude capture, queueing, storage and notification latency. Frames from the same clip are correlated; report recording-session counts and use session-level resampling or an appropriate study design for uncertainty before making an accuracy claim. No automated production approval is granted, regardless of scores.

## 3. Validate operational behavior at the site

Use a dedicated pilot tenant and test sinks; enable actual notifications only for explicitly authorized recipients. Review contiguous video and match confirmed events to independently labeled violation episodes. Measure missed episodes, duplicate/false alerts per observed camera-hour, capture-to-alert p50/p95 and reviewer disagreement for each PPE class and operating condition. Verify configured consecutive-frame voting, per-person tracking, cooldowns, confidence-review routing and maintenance suppression.

Test camera disconnect/reconnect, worker restart and temporary broker/storage interruption. Confirm that an outage is shown as unavailable rather than compliant. Run representative shifts at the planned concurrency on target hardware, recording frame freshness, processing/drop rates, GPU/CPU/memory use, queue backlog and recovery. Do not manufacture hazardous conditions to collect violations; use staged, supervised examples in a safe area.

Freeze acceptance targets before examining held-out results. The site report should state expand/retest/stop, with evidence and open defects. Do not replace these steps with synthetic events, a test pattern, a training validation split or a high aggregate score from unsupported classes.
