import os
import cv2
import numpy as np
import structlog
from dataclasses import dataclass
from typing import List
from ultralytics import YOLO

from src.config.settings import settings

log = structlog.get_logger()

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


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: tuple   # (x1, y1, x2, y2)
    is_violation: bool


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
                note="Using a generic COCO model — person detection only, no real PPE classes. "
                     "Replace with a fine-tuned PPE model for real violation detection.",
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
        processed = self.preprocess(frame)
        results = self._model(processed, verbose=False)[0]
        detections = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            if self._ppe_mode:
                class_name = PPE_CLASSES.get(cls_id, "unknown")
            else:
                class_name = self._model.names.get(cls_id, "unknown")
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            detections.append(Detection(
                class_name=class_name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
                is_violation=class_name in VIOLATION_CLASSES,
            ))

        return detections
