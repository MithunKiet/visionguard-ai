# Helmet and vest pilot: model selection decision

## Current decision

Pilot scope is helmet and safety-vest violations. YOLOv8s is an architecture candidate, **not an approved checkpoint**. No compatible, commercially reviewed production artifact has been selected or downloaded. The owner has no labeled factory dataset yet. A public-image baseline is now available in [PUBLIC_PPE_BASELINE.md](PUBLIC_PPE_BASELINE.md); those construction photos do not establish target-factory representativeness. Do not report a measured accuracy or camera budget.

The owner's Windows report verifies CUDA computation on an RTX 2000 Ada Laptop GPU (8188 MiB), PyTorch 2.6.0+cu124 and Python 3.11.9. This supports proceeding to model execution tests; it says nothing about PPE accuracy or sustained camera capacity.

## Compatibility evidence from this repository

`src/pipeline/detector.py` requires this exact production name/ID mapping:

| ID | Name |
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

Production also requires local weights, reviewed SHA-256, CUDA and demo mode disabled. Missing artifacts fail startup; production does not silently fall back to demo/remote inference. The validator uses explicit `no_helmet` and `no_vest` predictions. Missing positive-item boxes alone must not become violations. Person association and temporal voting must be validated as well as individual boxes.

A helmet/vest pilot can evaluate only those capabilities of a compatible nine-class model, with glove/shoe enforcement disabled in the pilot's effective policy. That does not validate other classes. A five-class model (`helmet`, `no_helmet`, `vest`, `no_vest`, `person`) needs an explicit supported-class contract change across detector readiness, evaluators, policy validation and tests before production use. Do not rename classes, pad an output dictionary with untrained classes or bypass the strict name check to make a checkpoint load.

## Candidate paths

| Candidate | Evidence available | Decision |
| --- | --- | --- |
| Existing six-class webcam ONNX trial | Pinned artifact/hash and source documented in PPE_WEBCAM_TRIAL.md; observed webcam false positives; separate preprocessing | Keep as a local experiment. Not compatible with the production `.pt` pipeline or capacity launcher. Publisher/license notes are not commercial approval. |
| Generic YOLOv8s COCO base | Suitable architecture candidate for fine-tuning; no trained PPE violation classes | Not a PPE deployment artifact. Review software/base-weight licensing before training or integration. |
| Trusted supplier nine-class PPE checkpoint | No artifact, license evidence or independent site metrics supplied yet | Preferred route to an initial unchanged-runtime candidate, conditional on the evidence checklist below. No supplier selected. |
| Factory fine-tuned candidate | No labeled training/development/held-out data yet | Prepare data first. Choose either the current nine-class training contract with real corresponding labels, or implement a reviewed smaller-class contract. Do not manufacture labels for unavailable classes. |

No new public checkpoint was independently audited in this selection pass. References for the existing experiment and Ultralytics terms are in [PPE_WEBCAM_TRIAL.md](PPE_WEBCAM_TRIAL.md); current terms and rights for the actual artifact/dataset must be reviewed before company use.

## Evidence required before accepting a candidate

Retain an artifact record containing:

- Supplier/publisher, immutable version/source and original artifact filename.
- Independently reviewed SHA-256, framework/export version, input size, exact class ID/name mapping and preprocessing/postprocessing expectations.
- Software, base-weight, final-weight and dataset license/provenance evidence; document commercial-use obligations and unresolved rights separately. A hash proves identity, not trust or licensing.
- Annotation conventions for person, helmet/head, vest/torso and explicit absence classes, including occlusion, partial PPE and ambiguous examples.
- Dataset origins and camera/session grouping for training, tuning and held-out evaluation; known overlap, exclusions and unsupported conditions.
- Independent per-class precision/recall, false positives and false negatives under fixed confidence/IoU settings. Vendor aggregate mAP is supplementary, not site acceptance.
- Intended runtime/version and known limitations. Do not load unknown PyTorch checkpoints merely to inspect their metadata: checkpoint loading itself requires trust.

## Execution order

1. Obtain the supplier evidence and candidate, or collect/review labeled data for a factory training path. Use authorized local data; do not upload it as part of this selection workflow.
2. Keep candidate files outside the active runtime model path. Verify identity and mapping, then run the bounded model-readiness CLI from [MODEL_READINESS.md](MODEL_READINESS.md).
3. Evaluate the production candidate with the production evaluation workflow in [REAL_CAMERA_VALIDATION.md](REAL_CAMERA_VALIDATION.md). The six-class webcam evaluator is not interchangeable. Agree on per-class/condition targets and independent sampling before reviewing held-out results.
4. Run [WINDOWS_GPU.md](WINDOWS_GPU.md)'s capacity sweep with representative stills and retain all reports. No label is needed for timing, but these stills cannot substitute for accuracy evaluation.
5. Run an authorized site pilot for person association, consecutive-frame voting, missed alerts, false alerts, camera freshness and sustained combined load. Promote only after the acceptance evidence and rollback artifact are reviewed.

## Training safeguards

The preparation CLI now requires a manifest and partitions whole cameras by default, or camera/session pairs with explicit `--group-by session`. Exact duplicate image bytes and invalid/missing labels are rejected. Near-duplicates, incorrect group metadata and synchronized views of the same event still require human review. The held-out test split must remain sealed during tuning.

Training now requires trusted local base weights plus a reviewed hash, creates a unique candidate run, evaluates its saved best checkpoint on the development split and writes hashes/metrics without copying anything into the runtime model path. Separate held-out accuracy, capacity, license review and explicit deployment remain required. See [MODEL_TRAINING.md](MODEL_TRAINING.md) for the changed CLI; the old `--source` random-image workflow is removed.
