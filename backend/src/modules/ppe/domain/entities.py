from dataclasses import dataclass
from datetime import datetime


@dataclass(kw_only=True)
class ViolationEntity:
    enterprise_id: str
    zone_id: str
    camera_id: str
    violation_type: str        # helmet_missing / vest_missing / gloves_missing / shoes_missing
    confidence: float
    needs_review: bool         # True for low-confidence detections
    created_at: datetime
    id: str | None = None      # public_id — unset until persisted
    snapshot_key: str | None = None
    track_id: str | None = None
    shift_id: str | None = None
    rule_id: str | None = None
    is_false_positive: bool = False
    fp_reason: str | None = None
    # Populated by the repository's joined list/get queries so the service
    # layer's enrich() needs zero extra DB round trips per row — see
    # infrastructure/repositories.py for why (N+1 query fix).
    zone_name: str | None = None
    camera_name: str | None = None
    camera_code: str | None = None
