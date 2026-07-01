from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ViolationEntity:
    id: UUID
    enterprise_id: UUID
    zone_id: UUID
    camera_id: UUID
    violation_type: str        # helmet_missing / vest_missing / gloves_missing / shoes_missing
    confidence: float
    snapshot_key: str | None
    track_id: str | None
    shift_id: UUID | None
    rule_id: UUID | None
    is_false_positive: bool
    fp_reason: str | None
    needs_review: bool         # True for low-confidence detections
    created_on: datetime
