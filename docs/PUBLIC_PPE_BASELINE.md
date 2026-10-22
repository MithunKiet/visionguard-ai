# Public-image helmet and vest baseline — 22 October 2026

Actual CPU inference was run with the existing pinned six-class webcam ONNX model on all **141 publisher test images** in Ultralytics Construction-PPE. This is an exploratory positive-object baseline, not model training, missing-vest violation validation or factory acceptance. No runtime weights or factory configuration were changed.

## Source and reproducibility

- Dataset: [Ultralytics Construction-PPE](https://docs.ultralytics.com/datasets/detect/construction-ppe/), authors Mrunmayee Dalvi, Niyati Singh, Sahil Bhingarde and Ketaki Chalke; publisher Ultralytics, version attributed upstream as 1.0.0 (2025).
- Download: [official release archive](https://github.com/ultralytics/assets/releases/download/v0.0.0/construction-ppe.zip).
- Downloaded archive SHA-256: `bef8dcb599aa4e9d9f5e602cb6fa7143d3c84d7f6a0ff40463d7f2a4c2632ccc`.
- The archive's LICENSE is GNU AGPL v3; its `data.yaml` and [publisher documentation source](https://github.com/ultralytics/ultralytics/blob/main/docs/en/datasets/detect/construction-ppe.md) identify AGPL-3.0. This is the publisher's license statement, not an independent chain-of-title or company commercial-use approval. Check obligations for the actual planned use; attribution alone does not discharge all AGPL obligations.
- Model: [pinned trial source and license notes](PPE_WEBCAM_TRIAL.md), SHA-256 `f7abd19f20a694c6422e7bb9fc647202e0c1cd5c78a3a28f123caeaa87d37098`. No model retraining or threshold tuning was performed for this test.
- Raw downloaded images/labels remain in ignored `validation-data/public-construction-ppe/`. Dataset images and weights are not committed or redistributed in this change.
- Full measured report: [public-ppe-baseline-20261022.json](evidence/public-ppe-baseline-20261022.json). It records source configuration and per-image/label hashes, frame-index errors and inference timings; it contains no image bytes.

The download contains 1,132 train images, 143 validation images and 141 test images. There are 1,142 train label files, so ten train-label files have no counted matching training image; investigate these before preparing training input. Test images all had parsable labels. The archive has 11 classes, not the production nine-class contract, and has **no `no_vest` class**.

## Method

Used every publisher test image, sorted by filename, without selecting examples based on model success. Confidence was fixed at **0.5**, matching IoU at **0.5**. Source class 0 is helmet and source class 2 is vest; predictions are selected by the trial model's semantic names. All other classes/predictions are outside this two-class study. Greedy confidence-ordered, one-to-one matching counts correct matched boxes as TP, unmatched predictions as FP, and unmatched annotations as FN.

No exact image-byte overlap was found between these 141 test images and the source train/val images; no exact test duplicate was excluded. Therefore raw and byte-filtered metrics are identical. This does **not** establish near-duplicate independence, camera/session separation or non-overlap with the existing model's PPE_master training data. Source camera/session identities are not supplied by this archive. Source annotations have not been independently reviewed. One visually inspected sample contains a real helmet and high-visibility vest; this spot check does not validate all box conventions or label completeness.

## Measured results

| Object | Labeled boxes | TP | FP | FN | Precision | Recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Helmet | 192 | 154 | 19 | 38 | 89.0% | 80.2% |
| Vest | 178 | 132 | 28 | 46 | 82.5% | 74.2% |

Precision measures the share of predictions matched to publisher labels; recall measures the share of publisher-labeled objects found. These are fixed-threshold object metrics, not mAP, percentage of safe workers, unique-person counts or event-level alert accuracy. The model missed 19.8% of labeled helmets and 25.8% of labeled vests in this exploratory set. A missed positive vest box must not automatically be interpreted as a missing-vest violation.

This run used cloud CPU and ONNX Runtime 1.23.2; timings are not measurements of the owner's laptop GPU. `training_performed=false`, `production_approved=false` and `missing_vest_accuracy_measured=false` remain explicit.

## Re-run

Use trusted local copies of the pinned model and archive. Extract into the ignored directory after verifying archive checksum. From `ai-worker`, with OpenCV, NumPy, ONNX Runtime and PyYAML installed:

```sh
python -m src.validation.public_ppe \
  --dataset ../validation-data/public-construction-ppe \
  --output ../validation-results/public-ppe-new-run.json
```

The evaluator checks source class names and pinned model checksum, reports invalid input exclusions and never overwrites an existing report. `reference_archive_sha256` identifies the archive used in this documented run; the evaluator does not automatically verify the entire local dataset against that archive. Per-file hashes identify what was actually scored. It never runs training or alters production settings.

## Training suitability and next work

These online images provide a labeled public starting point for helmet/vest object experiments. They are not a drop-in production training dataset: class contracts differ, missing-vest labels are absent, camera/session grouping is unknown and image rights/annotation quality need review for intended company use. Do not fabricate session IDs, pad the class list or convert every absent vest prediction into a violation.

Before production training, review and add the required absence annotations, resolve class capability support, establish independent grouped development/held-out data, and retain dataset/license provenance. The present baseline supports targeted error review and further data collection; it does not select or approve a new production model. Keep the already-inspected public test set separate from any future training; if it is used to tune decisions, reserve new independent acceptance data.

Tool verification: 19 public/evaluation regression tests passed; one optional actual-model test was skipped in that unit invocation. Separately, this baseline executed the real pinned ONNX model on all 141 public images. The four new tests check semantic class mapping, exact-overlap filtering, rejected-input accounting and incorrect source mappings.
