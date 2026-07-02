"""
Fine-tune YOLOv8 on the factory PPE dataset (master context rule #15: never
ship COCO-pretrained weights to production).

Usage:
    python train.py                          # defaults: yolov8s, 100 epochs
    python train.py --model yolov8m.pt --epochs 150 --imgsz 960

Output:
    runs/ppe/weights/best.pt  → copy to ai-worker/models/yolov8s-ppe.pt
                                (the path in WorkerSettings.YOLO_MODEL_PATH)

Validation gate before deploying (Section 17): helmet-class mAP@50 ≥ 0.85 on
a held-out set of REAL footage from the target factory's cameras — not just
the training-distribution val split.
"""
import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="yolov8s.pt", help="Base checkpoint to fine-tune")
    parser.add_argument("--data", default="dataset.yaml", help="Dataset config")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0", help="'0' for GPU 0, 'cpu' for CPU")
    parser.add_argument("--export-onnx", action="store_true", help="Also export best.pt to ONNX")
    args = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project="runs",
        name="ppe",
        exist_ok=True,
        # Factory-floor robustness: keep the default augmentations plus
        # brightness/contrast jitter to cover lighting variation.
        hsv_v=0.5,
        degrees=5.0,
    )

    best = Path("runs/ppe/weights/best.pt")
    if not best.exists():
        raise SystemExit("Training finished but best.pt not found — check runs/ppe/")

    metrics = model.val(data=args.data)
    print(f"\nmAP@50: {metrics.box.map50:.3f}   mAP@50-95: {metrics.box.map:.3f}")

    target = Path(__file__).resolve().parent.parent / "models" / "yolov8s-ppe.pt"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, target)
    print(f"Deployed weights → {target}")

    if args.export_onnx:
        YOLO(str(best)).export(format="onnx", imgsz=args.imgsz)
        print("ONNX export complete (runs/ppe/weights/best.onnx)")

    print("\nRestart the AI worker (or push a model_updated config event) to load the new model.")


if __name__ == "__main__":
    main()
