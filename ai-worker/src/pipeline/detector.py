import os
import sys

# The container's apt python3.11 package is a pre-release build (3.11.0~rc1)
# missing sys.get_int_max_str_digits / sys.set_int_max_str_digits, added only
# late in the 3.11 release cycle. torch._dynamo's polyfills module imports
# them unconditionally (torch/_dynamo/polyfills/sys.py) and validates the
# polyfill's signature against the original, so the shim names/signatures
# below must match exactly.
_int_max_str_digits = 4300

if not hasattr(sys, "get_int_max_str_digits"):
    def get_int_max_str_digits() -> int:
        return _int_max_str_digits
    sys.get_int_max_str_digits = get_int_max_str_digits

if not hasattr(sys, "set_int_max_str_digits"):
    def set_int_max_str_digits(maxdigits: int) -> None:
        global _int_max_str_digits
        _int_max_str_digits = maxdigits
    sys.set_int_max_str_digits = set_int_max_str_digits

import time

import cv2
import numpy as np
import structlog
from typing import List
from ultralytics import YOLO

from src.config.settings import settings
from src.pipeline.types import Detection

log = structlog.get_logger()

# Demo mode only (no fine-tuned PPE model): which synthetic violation type is
# "active" cycles on a fixed schedule rather than per-frame-random, since
# PPEValidator requires 3 CONSECUTIVE frames of the SAME type before
# confirming a violation (see ppe_validator.py) — a type that changes every
# frame would never accumulate enough consecutive frames to fire at all.
# Kept stable for DEMO_ROTATION_SECONDS at a time so each type gets a fair
# chance to confirm and fire before rotating to the next.
DEMO_VIOLATION_TYPES = ["no_helmet", "no_vest", "no_gloves", "no_safety_shoes"]
DEMO_ROTATION_SECONDS = 20

# Which body zone each demo violation type needs visible in the frame. There's
# no real pose estimation in demo mode — this is a coarse geometry heuristic
# off the person bbox (e.g. a face/upper-body close-up shouldn't ever be able
# to fire "shoes missing", since feet aren't in frame at all) so the fake
# labels at least stay plausible for the shot, even though they're not real
# PPE detection.
ZONE_FOR_TYPE = {
    "no_helmet": "head",
    "no_vest": "torso",
    "no_gloves": "torso",
    "no_safety_shoes": "feet",
}
# Fraction of frame height the bbox's bottom edge must reach for "feet" to
# count as visible — a tight face/shoulders shot ends well above this.
FEET_VISIBLE_BOTTOM_FRAC = 0.80
# A standing full body is much taller than wide (~2.5-4x); a close-up shot
# with an arm/hand reaching toward the bottom of frame (common with laptop
# webcams) can also push the bbox bottom edge down without feet being in
# frame at all, so the bottom-edge check alone isn't reliable — require the
# bbox shape to actually look like a standing body too.
FEET_VISIBLE_MIN_ASPECT = 1.6

PPE_CLASSES = {
    0: "helmet",
    1: "no_helmet",
    2: "vest",
    3: "no_vest",
    4: "gloves",
    5: "no_gloves",
    6: "safety_shoes",
    7: "no_safety_shoes",
    8: "person",
}

VIOLATION_CLASSES = {"no_helmet", "no_vest", "no_gloves", "no_safety_shoes"}

# Fallback for the pilot when no fine-tuned PPE weights are present at
# YOLO_MODEL_PATH: use a generic pretrained COCO model so the pipeline still
# runs end-to-end (person detection only, no real PPE violation classes).
_FALLBACK_MODEL = "yolov8n.pt"


class PPEDetector:

    def __init__(self):
        device = "cuda" if settings.USE_GPU else "cpu"

        self._ppe_mode = os.path.isfile(settings.YOLO_MODEL_PATH)
        model_path = settings.YOLO_MODEL_PATH if self._ppe_mode else _FALLBACK_MODEL

        if not self._ppe_mode:
            log.warning(
                "detector.ppe_model_missing",
                expected=settings.YOLO_MODEL_PATH,
                fallback=_FALLBACK_MODEL,
                note="Using a generic COCO model. DEMO MODE: any detected 'person' is reported "
                     "as a synthetic violation (rotating through helmet/vest/gloves/shoes every "
                     f"{DEMO_ROTATION_SECONDS}s) so the pipeline and UI can be exercised end-to-end "
                     "against real camera frames. Replace with a fine-tuned PPE model for real "
                     "violation detection.",
            )

        log.info("detector.loading", model=model_path, device=device)
        self._model = YOLO(model_path)
        self._model.to(device)
        log.info("detector.ready", device=device, ppe_mode=self._ppe_mode)

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Rule 13: CLAHE preprocessing on every frame before YOLO inference."""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = cv2.merge([clahe.apply(l), a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        return self.detect_batch([frame])[0]

    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        """
        Run inference on multiple camera frames in a single forward pass.
        A GPU processes a batch of N images far more efficiently than N
        sequential single-image calls (better utilization of parallel
        compute per call), so this is what lets one GPU serve more cameras
        — BatchDetector groups pending per-camera frames and calls this.
        """
        processed = [self.preprocess(f) for f in frames]
        results_list = self._model(processed, verbose=False)
        return [self._parse_results(r) for r in results_list]

    @staticmethod
    def _visible_zones(x1: int, y1: int, x2: int, y2: int, frame_height: int) -> set:
        """Coarse "is this body part plausibly in frame" heuristic from bbox
        geometry alone. Head/torso are assumed visible whenever a person is
        detected at all; feet only count as visible once the box's bottom
        edge reaches near the bottom of the frame AND the box is shaped like
        a standing body (tall/narrow) rather than a close-up (wide/short)."""
        zones = {"head", "torso"}
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        bottom_frac = (y2 / frame_height) if frame_height else 1.0
        aspect = height / width
        if bottom_frac >= FEET_VISIBLE_BOTTOM_FRAC and aspect >= FEET_VISIBLE_MIN_ASPECT:
            zones.add("feet")
        return zones

    def _parse_results(self, results) -> List[Detection]:
        detections = []
        frame_height = results.orig_shape[0] if getattr(results, "orig_shape", None) else None

        for box in results.boxes:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            if self._ppe_mode:
                class_name = PPE_CLASSES.get(cls_id, "unknown")
                is_violation = class_name in VIOLATION_CLASSES
            else:
                class_name = self._model.names.get(cls_id, "unknown")
                is_violation = False
                # Demo mode: no fine-tuned PPE model is loaded, so there's no
                # real helmet/vest/gloves/shoes signal to violate. Emit the
                # person detection itself (so occupancy counting still works),
                # plus a synthetic violation — type rotates on a fixed
                # schedule (see DEMO_VIOLATION_TYPES/DEMO_ROTATION_SECONDS
                # above), skipped when the current slot's body zone isn't
                # plausibly visible for this bbox (e.g. never "shoes missing"
                # on a face/upper-body close-up) — so the rest of the
                # pipeline (snapshot capture, MinIO upload, alert, dashboard)
                # can be exercised end-to-end against real camera frames,
                # across all violation types, without nonsensical labels.
                if class_name == "person":
                    demo_type = DEMO_VIOLATION_TYPES[
                        int(time.monotonic() // DEMO_ROTATION_SECONDS) % len(DEMO_VIOLATION_TYPES)
                    ]
                    visible = self._visible_zones(x1, y1, x2, y2, frame_height)
                    if ZONE_FOR_TYPE[demo_type] in visible:
                        detections.append(Detection(
                            class_name=demo_type,
                            confidence=confidence,
                            bbox=(x1, y1, x2, y2),
                            is_violation=True,
                        ))

            detections.append(Detection(
                class_name=class_name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
                is_violation=is_violation,
            ))

        return detections
