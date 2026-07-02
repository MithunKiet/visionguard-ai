import time
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

DEFAULT_COOLDOWN_SECONDS = 120


class ViolationTracker:
    """Rule 14: Multi-frame voting — require REQUIRED_CONSECUTIVE_FRAMES
    consecutive positive detections before confirming a violation.

    Also throttles repeat firing of the same violation type: once confirmed,
    the same key won't fire (snapshot + event) again until cooldown_seconds
    has passed, even if the subject stays in frame continuously — otherwise
    a single person standing still gets a new snapshot + DB row on every
    processed frame (2x/sec by default)."""

    def __init__(self):
        self._counts: Dict[str, int] = {}
        self._last_fired: Dict[str, float] = {}

    def record(self, key: str, violation: bool, required_frames: int) -> bool:
        if violation:
            self._counts[key] = self._counts.get(key, 0) + 1
        else:
            self._counts[key] = 0
        return self._counts[key] >= required_frames

    def should_fire(self, key: str, cooldown_seconds: int) -> bool:
        last = self._last_fired.get(key)
        return last is None or (time.monotonic() - last) >= cooldown_seconds

    def mark_fired(self, key: str) -> None:
        self._last_fired[key] = time.monotonic()
        self._counts[key] = 0  # require fresh consecutive-frame confirmation after cooldown

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
        cooldown_seconds = zone_config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
        required_frames = zone_config.get("required_consecutive_frames", settings.REQUIRED_CONSECUTIVE_FRAMES)
        low_confidence_floor = zone_config.get("low_confidence_floor", settings.LOW_CONFIDENCE_FLOOR)

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
                if self._tracker.record(key, True, required_frames) and self._tracker.should_fire(key, cooldown_seconds):
                    self._tracker.mark_fired(key)
                    confirmed.append({
                        "event": event_name,
                        "confidence": det.confidence,
                        "bbox": det.bbox,
                        "review": False,
                    })
            elif det.confidence >= low_confidence_floor:
                key = f"review:{det.class_name}"
                if self._tracker.should_fire(key, cooldown_seconds):
                    self._tracker.mark_fired(key)
                    confirmed.append({
                        "event": "low_confidence_violation",
                        "violation_type": det.class_name,
                        "confidence": det.confidence,
                        "bbox": det.bbox,
                        "review": True,
                    })
            else:
                self._tracker.record(det.class_name, False, required_frames)

        return confirmed
