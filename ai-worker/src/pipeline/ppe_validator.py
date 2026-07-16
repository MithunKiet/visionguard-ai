import time
import structlog
from typing import Dict
from src.pipeline.types import Detection
from src.pipeline.person_tracker import PersonTracker, containment_ratio, iou
from src.config.settings import settings

log = structlog.get_logger()

VIOLATION_TO_EVENT = {
    "no_helmet":       "helmet_missing_detected",
    "no_vest":         "vest_missing_detected",
    "no_gloves":       "gloves_missing_detected",
    "no_safety_shoes": "shoes_missing_detected",
}

# Maps each violation class to the item name used in zone_configs.ppe_required
# (e.g. ["helmet", "vest"]) — a zone that doesn't require an item shouldn't be
# flagged for missing it, regardless of what the detector reports.
VIOLATION_TO_ITEM = {
    "no_helmet":       "helmet",
    "no_vest":         "vest",
    "no_gloves":       "gloves",
    "no_safety_shoes": "shoes",
}

DEFAULT_PPE_REQUIRED = ["helmet", "vest"]
DEFAULT_COOLDOWN_SECONDS = 120

# A violation box must overlap a person box by at least this much of the
# violation box's own area to be considered "that person's" violation (see
# _match_person below) — below this it's treated as unassociated.
PERSON_MATCH_MIN_CONTAINMENT = 0.3


class ViolationTracker:
    """Rule 14: Multi-frame voting — require REQUIRED_CONSECUTIVE_FRAMES
    consecutive positive detections before confirming a violation.

    Also throttles repeat firing of the same violation type: once confirmed,
    the same key won't fire (snapshot + event) again until cooldown_seconds
    has passed, even if the subject stays in frame continuously — otherwise
    a single person standing still gets a new snapshot + DB row on every
    processed frame (2x/sec by default).

    Keys are "{violation_class}:{person_track_id}" (see PPEValidator) so two
    different people missing the same PPE item are counted/cooled down
    independently instead of sharing one counter."""

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

    def forget_track(self, track_id: int) -> None:
        """Drop all state for a person who's left the frame (PersonTracker
        expired them) — otherwise _counts/_last_fired grow without bound over
        a long-running camera stream, and a stale entry could let a
        different, later person who happens to reuse that track_id inherit
        a partial count or an active cooldown that isn't theirs."""
        suffix = f":{track_id}"
        for d in (self._counts, self._last_fired):
            for key in [k for k in d if k.endswith(suffix)]:
                del d[key]


class PPEValidator:

    def __init__(self):
        self._tracker = ViolationTracker()
        self._people = PersonTracker()

    def _match_person(self, violation_bbox: tuple, people: list[tuple[tuple, int]]) -> int | None:
        """Best-matching person track_id for a violation box. In remote
        (Roboflow) and demo mode the violation bbox IS the person's own bbox
        (see detector.py), so this is an exact/trivial match; in local
        fine-tuned-model mode a violation box is typically a smaller region
        (e.g. head-only for no_helmet), so containment — how much of the
        violation box sits inside a given person box — is the better signal
        than plain IOU, with IOU kept as a fallback for edge cases."""
        best_id, best_score = None, 0.0
        for person_bbox, track_id in people:
            score = max(
                containment_ratio(violation_bbox, person_bbox),
                iou(violation_bbox, person_bbox),
            )
            if score > best_score:
                best_id, best_score = track_id, score
        return best_id if best_score >= PERSON_MATCH_MIN_CONTAINMENT else None

    def evaluate(self, detections: list[Detection], zone_config: dict) -> list[dict]:
        """
        Returns list of confirmed violations.
        Rule 16: Routes low-confidence detections to review queue instead of alert.
        """
        confirmed = []
        cooldown_seconds = zone_config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)
        required_frames = zone_config.get("required_consecutive_frames", settings.REQUIRED_CONSECUTIVE_FRAMES)
        low_confidence_floor = zone_config.get("low_confidence_floor", settings.LOW_CONFIDENCE_FLOOR)
        ppe_required = zone_config.get("ppe_required") or DEFAULT_PPE_REQUIRED

        person_boxes = [det.bbox for det in detections if det.class_name == "person"]
        track_ids, expired_ids = self._people.update(person_boxes)
        people = list(zip(person_boxes, track_ids))
        for expired_id in expired_ids:
            self._tracker.forget_track(expired_id)

        for det in detections:
            if not det.is_violation:
                continue

            event_name = VIOLATION_TO_EVENT.get(det.class_name)
            if not event_name:
                continue

            item = VIOLATION_TO_ITEM.get(det.class_name)
            if item and item not in ppe_required:
                # This zone doesn't require this PPE item — not a violation here.
                continue

            threshold = zone_config.get(f"{det.class_name.replace('no_', '')}_threshold",
                                        settings.SNAPSHOT_CONFIDENCE_THRESHOLD)

            # "unmatched" (rather than skipping) so a violation whose person
            # box wasn't detected this frame (e.g. partially occluded) still
            # gets tracked/gated, just not attributed to a specific individual.
            track_id = self._match_person(det.bbox, people)
            track_key = track_id if track_id is not None else "unmatched"

            if det.confidence >= threshold:
                key = f"{det.class_name}:{track_key}"
                if self._tracker.record(key, True, required_frames) and self._tracker.should_fire(key, cooldown_seconds):
                    self._tracker.mark_fired(key)
                    confirmed.append({
                        "event": event_name,
                        "confidence": det.confidence,
                        "bbox": det.bbox,
                        "review": False,
                    })
            elif det.confidence >= low_confidence_floor:
                key = f"review:{det.class_name}:{track_key}"
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
                self._tracker.record(f"{det.class_name}:{track_key}", False, required_frames)

        return confirmed
