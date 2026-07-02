"""
Dataset preparation for PPE fine-tuning.

Takes a flat folder of labeled images (YOLO txt format, one .txt per image)
and splits it into the train/val layout Ultralytics expects:

    datasets/ppe/
    ├── images/train/  images/val/
    └── labels/train/  labels/val/

Usage:
    python prepare_dataset.py --source ./raw_labeled --out ./datasets/ppe --val-split 0.2

Labeling guidance (master context Section 17 / Risk 1):
- 500–2,000 images per PPE class minimum
- include variable lighting, occlusion, wide angles, night/IR shots
- label BOTH positive (helmet) and negative (no_helmet) classes
"""
import argparse
import random
import shutil
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Folder with images + YOLO .txt labels")
    parser.add_argument("--out", default="./datasets/ppe", help="Output dataset root")
    parser.add_argument("--val-split", type=float, default=0.2, help="Validation fraction")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)

    images = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    labeled = [p for p in images if p.with_suffix(".txt").exists()]
    skipped = len(images) - len(labeled)
    if skipped:
        print(f"WARNING: {skipped} images have no .txt label and are skipped")
    if not labeled:
        raise SystemExit("No labeled images found — nothing to do")

    random.Random(args.seed).shuffle(labeled)
    val_count = max(1, int(len(labeled) * args.val_split))
    splits = {"val": labeled[:val_count], "train": labeled[val_count:]}

    for split, files in splits.items():
        img_dir = out / "images" / split
        lbl_dir = out / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        for img in files:
            shutil.copy2(img, img_dir / img.name)
            shutil.copy2(img.with_suffix(".txt"), lbl_dir / img.with_suffix(".txt").name)
        print(f"{split}: {len(files)} images")

    print(f"\nDataset ready at {out}. Next: copy dataset.yaml.example to dataset.yaml,")
    print("set `path` to this folder, then run: python train.py")


if __name__ == "__main__":
    main()
