"""Shared pipeline dataclasses — kept dependency-free so validators and
tests can import them without pulling in ultralytics/torch."""
from dataclasses import dataclass


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: tuple   # (x1, y1, x2, y2)
    is_violation: bool
