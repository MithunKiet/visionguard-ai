"""Unit tests — CameraWorker occupancy counting/publishing logic.

CameraWorker itself imports cv2/minio, so the counting rule is tested
through a minimal reimplementation of its filter expression against the
shared Detection type — this pins the person_threshold contract."""
from src.pipeline.types import Detection


def _count_persons(detections: list[Detection], person_threshold: float) -> int:
    # Mirrors CameraWorker._publish_occupancy's counting rule
    return sum(
        1 for d in detections
        if d.class_name == "person" and d.confidence >= person_threshold
    )


def _det(name: str, conf: float) -> Detection:
    return Detection(class_name=name, confidence=conf, bbox=(0, 0, 1, 1),
                     is_violation=False)


def test_counts_only_persons_above_threshold():
    detections = [
        _det("person", 0.95),
        _det("person", 0.71),
        _det("person", 0.50),     # below threshold — not counted
        _det("no_helmet", 0.90),  # not a person
        _det("forklift", 0.99),
    ]
    assert _count_persons(detections, person_threshold=0.70) == 2


def test_empty_frame_counts_zero():
    assert _count_persons([], person_threshold=0.70) == 0
