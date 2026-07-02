# PPE Model Training Guide

The AI worker requires a **fine-tuned PPE detection model** at
`ai-worker/models/yolov8s-ppe.pt`. Until one is present, the worker runs in
**demo mode**: a generic COCO YOLOv8 model detects people (so occupancy
counting works) and reports every person as a synthetic `helmet_missing`
violation so the full pipeline can be exercised end-to-end.

> Master context rule #15: **never use COCO-pretrained weights in
> production.** Demo mode is for pipeline validation only.

## 1. Collect footage

Pull frames from the actual factory cameras the model will run on — training
on internet PPE datasets alone will not survive your lighting, angles, and
uniforms. Cover:

- All shifts (day, evening, night/IR)
- Occlusion: workers behind machines, partial views, crowds
- All PPE states: worn correctly, missing, worn incorrectly

**Minimum: 500–2,000 labeled images per class** (Risk 1, BRD).

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
