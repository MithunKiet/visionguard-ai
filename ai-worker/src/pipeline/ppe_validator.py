import structlog
from typing import Dict
from src.pipeline.detector import Detection
from src.config.settings import settings

log = structlog.get_logger()

VIOLATION_TO_EVENT = {
    "no_helmet":       "helmet_missing_detected",
    "no_vest":         "vest_missing_detected",
    "no_gloves":       "gloves_missing_detected",
    "no_safety_shoes": "shoes_missing_detected",
}


class ViolationTracker:
    """Rule 14: Multi-frame voting — require REQUIRED_CONSECUTIVE_FRAMES
    consecutive positive detections before confirming a violation."""

    def __init__(self):
        self._counts: Dict[str, int] = {}

    def record(self, key: str, violation: bool) -> bool:
        if violation:
            self._counts[key] = self._counts.get(key, 0) + 1
        else:
            self._counts[key] = 0
        return self._counts[key] >= settings.REQUIRED_CONSECUTIVE_FRAMES

    def reset(self, key: str) -> None:
        self._counts.pop(key, None)


class PPEValidator:

    def __init__(self):
        self._tracker = ViolationTracker()

    def evaluate(self, detections: list[Detection], zone_config: dict) -> list[dict]:
        """
        Returns list of confirmed violations.
        Rule 16: Routes low-confidence detections to review queue instead of alert.
        """
        confirmed = []

        for det in detections:
            if not det.is_violation:
                continue

            event_name = VIOLATION_TO_EVENT.get(det.class_name)
            if not event_name:
                continue

            threshold = zone_config.get(f"{det.class_name.replace('no_', '')}_threshold",
                                        settings.SNAPSHOT_CONFIDENCE_THRESHOLD)

            if det.confidence >= threshold:
                key = det.class_name
                if self._tracker.record(key, True):
                    confirmed.append({
                        "event": event_name,
                        "confidence": det.confidence,
                        "bbox": det.bbox,
                        "review": False,
                    })
            elif det.confidence >= settings.LOW_CONFIDENCE_FLOOR:
                confirmed.append({
                    "event": "low_confidence_violation",
                    "violation_type": det.class_name,
                    "confidence": det.confidence,
                    "bbox": det.bbox,
                    "review": True,
                })
            else:
                self._tracker.record(det.class_name, False)

        return confirmed
