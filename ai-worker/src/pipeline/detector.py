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


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: tuple   # (x1, y1, x2, y2)
    is_violation: bool


class PPEDetector:

    def __init__(self):
        device = "cuda" if settings.USE_GPU else "cpu"
        log.info("detector.loading", model=settings.YOLO_MODEL_PATH, device=device)
        self._model = YOLO(settings.YOLO_MODEL_PATH)
        self._model.to(device)
        log.info("detector.ready", device=device)

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
            class_name = PPE_CLASSES.get(cls_id, "unknown")
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            detections.append(Detection(
                class_name=class_name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
                is_violation=class_name in VIOLATION_CLASSES,
            ))

        return detections
