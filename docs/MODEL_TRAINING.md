# PPE Model Training Guide

The production AI worker requires a trusted, fine-tuned PPE checkpoint, its reviewed SHA-256 and CUDA. Missing production weights fail startup; demo/remote fallback is forbidden in production.

Read [PPE_MODEL_SELECTION.md](PPE_MODEL_SELECTION.md) before using this legacy training workflow. Its random image split is not an independent factory evaluation split, and `train.py` automatically copies weights into the runtime path. Run training only in an isolated checkout until explicit candidate promotion is implemented. A completed training run does not approve deployment.

## 1. Collect footage

Pull frames from the actual factory cameras the model will run on — training
on internet PPE datasets alone will not survive your lighting, angles, and
uniforms. Cover:

- All shifts (day, evening, night/IR)
- Occlusion: workers behind machines, partial views, crowds
- All PPE states: worn correctly, missing, worn incorrectly

The historical planning estimate was 500–2,000 labeled images per class; this is not a statistical sufficiency or production acceptance guarantee. Coverage and independent camera/session groups matter.

## 2. Label

Use any YOLO-format labeling tool (Label Studio, CVAT, Roboflow). The class
order **must match** `PPE_CLASSES` in `ai-worker/src/pipeline/detector.py`:

| ID | Class | ID | Class |
|---|---|---|---|
| 0 | helmet | 4 | gloves |
| 1 | no_helmet | 5 | no_gloves |
| 2 | vest | 6 | safety_shoes |
| 3 | no_vest | 7 | no_safety_shoes |
| | | 8 | person |

Label **both** positive and negative classes — the validator alerts on
`no_*` detections, so "no_helmet" must be an explicitly trained class, not
just the absence of "helmet".

## 3. Prepare the dataset

```bash
cd ai-worker/training
python prepare_dataset.py --source ./raw_labeled --out ./datasets/ppe --val-split 0.2
cp dataset.yaml.example dataset.yaml   # then set `path:` to ./datasets/ppe
```

## 4. Train

```bash
pip install ultralytics
python train.py --model yolov8s.pt --epochs 100 --device 0
# CPU-only machine: python train.py --device cpu (slow; use a GPU box or Colab)
```

The script validates after training, prints mAP, and copies `best.pt` to
`ai-worker/models/yolov8s-ppe.pt` automatically.

## 5. Validation gate (before production)

From `AI_MASTER_CONTEXT.md` Section 17 — all must pass **on real footage from
the target factory's cameras**, not the training val split:

- [ ] Helmet detection accuracy ≥ 85% (target ≥ 90% after iteration)
- [ ] False positive rate ≤ 5% over a full shift of footage
- [ ] Inference ≥ 10 FPS per stream on the deployment GPU

If accuracy falls short, first check **camera placement** against Section 18
(3–5 m height, 30–45° tilt, ≥ 1080p @ 15 FPS, ≥ 150 LUX) — placement problems
degrade accuracy more than model problems.

## 6. Deploy

```bash
# The worker loads the model at startup:
docker compose restart ai-worker
# Expect in logs: detector.loading model=models/yolov8s-ppe.pt, ppe_mode=True
```

Version retired models in the MinIO `models/` bucket
(`models/yolo/v1.x/weights.pt`) so any deployment can be rolled back.
