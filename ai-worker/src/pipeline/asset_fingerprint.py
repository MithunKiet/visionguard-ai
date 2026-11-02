"""Model-free reference fingerprints for fixed safety assets.

Keep this file byte-identical with ai-worker/src/pipeline/asset_fingerprint.py
(a backend test enforces it): the API derives reference fingerprints and the
worker derives live ones, so both sides must reduce frames the same way.

A fingerprint only says whether a region still looks like its reference. It
cannot tell a missing extinguisher from a displaced or covered one.
"""
import base64
import math

import cv2
import numpy as np

ROI_SIZE = (32, 32)     # (width, height)
SCENE_SIZE = (32, 18)
MIN_ROI = 0.02
# Below this pixel standard deviation a patch has no usable structure, so
# correlation is meaningless and brightness is compared instead.
FLAT_STD = 2.0


def validate_roi(x, y, width, height):
    values = (x, y, width, height)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) for v in values):
        raise ValueError("ROI values must be numbers")
    if x < 0 or y < 0 or width < MIN_ROI or height < MIN_ROI or x + width > 1 + 1e-9 or y + height > 1 + 1e-9:
        raise ValueError("ROI must lie inside the frame and cover at least 2% of each side")


def _gray(image):
    if image is None or image.ndim not in (2, 3) or image.shape[0] < 2 or image.shape[1] < 2:
        raise ValueError("Invalid image")
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image


def roi_box(shape, roi):
    """Pixel box (x0, y0, x1, y1) for a normalized (x, y, width, height) ROI."""
    height, width = shape[:2]
    x0 = min(width - 1, max(0, round(roi[0] * width)))
    y0 = min(height - 1, max(0, round(roi[1] * height)))
    x1 = min(width, max(x0 + 1, round((roi[0] + roi[2]) * width)))
    y1 = min(height, max(y0 + 1, round((roi[1] + roi[3]) * height)))
    return x0, y0, x1, y1


def roi_fingerprint(image, roi):
    gray = _gray(image)
    x0, y0, x1, y1 = roi_box(gray.shape, roi)
    return cv2.resize(gray[y0:y1, x0:x1], ROI_SIZE, interpolation=cv2.INTER_AREA)


def scene_fingerprint(image):
    return cv2.resize(_gray(image), SCENE_SIZE, interpolation=cv2.INTER_AREA)


def encode(fingerprint):
    return base64.b64encode(np.ascontiguousarray(fingerprint, dtype=np.uint8).tobytes()).decode("ascii")


def decode(text, size):
    raw = base64.b64decode(text.encode("ascii"), validate=True)
    if len(raw) != size[0] * size[1]:
        raise ValueError("Fingerprint size mismatch")
    return np.frombuffer(raw, dtype=np.uint8).reshape(size[1], size[0])


def scene_similarity(live, reference, roi):
    """Whole-view similarity excluding the asset's own ROI (plus one cell of
    margin), so a removed asset never reads as a moved or covered camera."""
    rows, cols = SCENE_SIZE[1], SCENE_SIZE[0]
    x0, y0, x1, y1 = roi_box((rows, cols), roi)
    mask = np.ones((rows, cols), dtype=bool)
    mask[max(0, y0 - 1):min(rows, y1 + 1), max(0, x0 - 1):min(cols, x1 + 1)] = False
    if mask.sum() < (rows * cols) // 4:
        mask[:] = True  # An ROI covering most of the view leaves too little context.
    return similarity(np.asarray(live)[mask], np.asarray(reference)[mask])


def similarity(a, b):
    """Zero-mean normalized correlation in [-1, 1]; tolerant of uniform lighting."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    if a.shape != b.shape:
        raise ValueError("Fingerprint shape mismatch")
    std_a, std_b = float(a.std()), float(b.std())
    if std_a < FLAT_STD or std_b < FLAT_STD:
        return float(max(0.0, 1.0 - abs(float(a.mean()) - float(b.mean())) / 64.0))
    correlation = float(((a - a.mean()) * (b - b.mean())).mean()) / (std_a * std_b)
    return float(max(-1.0, min(1.0, correlation)))
