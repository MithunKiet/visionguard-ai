"""Frame-level, class-aware object matching. These are not alert/event metrics."""
import math


def box_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


def valid_box(box):
    return (len(box) == 4 and all(math.isfinite(v) and v >= 0 for v in box)
            and box[0] < box[2] and box[1] < box[3])


def score_frame(truth, predictions, classes, confidence=0.6, iou_threshold=0.5):
    if not 0 <= confidence <= 1 or not 0 < iou_threshold <= 1:
        raise ValueError("Invalid scoring threshold")
    if not classes or len(set(classes)) != len(classes):
        raise ValueError("Classes must be nonempty and unique")
    for row in truth + predictions:
        if row["class_name"] not in classes or not valid_box(row["bbox"]):
            raise ValueError("Invalid annotation or prediction")
    for row in predictions:
        if not math.isfinite(row["confidence"]) or not 0 <= row["confidence"] <= 1:
            raise ValueError("Invalid prediction confidence")
    result = {}
    for name in classes:
        targets = [row["bbox"] for row in truth if row["class_name"] == name]
        candidates = sorted((row for row in predictions if row["class_name"] == name and row["confidence"] >= confidence),
                            key=lambda row: row["confidence"], reverse=True)
        remaining = set(range(len(targets)))
        true_positive = 0
        for row in candidates:
            best = max(remaining, key=lambda i: box_iou(row["bbox"], targets[i]), default=None)
            if best is not None and box_iou(row["bbox"], targets[best]) >= iou_threshold:
                true_positive += 1
                remaining.remove(best)
        result[name] = {"tp": true_positive, "fp": len(candidates) - true_positive, "fn": len(remaining)}
    return result


def summarize(counts):
    result = {}
    for name, row in counts.items():
        tp, fp, fn = row["tp"], row["fp"], row["fn"]
        result[name] = {**row, "support": tp + fn,
                        "precision": tp / (tp + fp) if tp + fp else None,
                        "recall": tp / (tp + fn) if tp + fn else None}
    return result


def read_yolo_labels(path, width, height, classes):
    """An explicit empty label file is a negative frame; missing is an error."""
    truth = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError("A label must contain a class ID and four coordinates")
        class_id = int(parts[0])
        x, y, w, h = map(float, parts[1:])
        if (not 0 <= class_id < len(classes) or not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y, w, h))
                or w <= 0 or h <= 0 or min(x-w/2, y-h/2) < -1e-6 or max(x+w/2, y+h/2) > 1+1e-6):
            raise ValueError("Invalid normalized label coordinates")
        truth.append({"class_name": classes[class_id], "bbox": [max(0, (x-w/2)*width), max(0, (y-h/2)*height),
                                                                  min(width, (x+w/2)*width), min(height, (y+h/2)*height)]})
    return truth
