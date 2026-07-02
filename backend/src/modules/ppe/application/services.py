"""
PPEService — save violations from RabbitMQ events, serve API queries.
"""
import uuid
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.core.exceptions import NotFoundException
from src.modules.ppe.domain.entities import ViolationEntity
from src.modules.ppe.infrastructure.repositories import ViolationRepository
from src.shared.storage.minio_client import get_presigned_url

log = structlog.get_logger()

# Map RabbitMQ routing key → violation_type stored in DB
ROUTING_KEY_TO_TYPE = {
    "events.helmet_missing_detected": "helmet_missing",
    "events.vest_missing_detected":   "vest_missing",
    "events.gloves_missing_detected": "gloves_missing",
    "events.shoes_missing_detected":  "shoes_missing",
    "events.mask_missing_detected":   "mask_missing",
}


class PPEService:

    def __init__(self, repo: ViolationRepository):
        self._repo = repo

    # ── Called by RabbitMQ consumer ────────────────────────────────────────

    async def handle_violation_event(self, routing_key: str, body: dict) -> ViolationEntity:
        violation_type = ROUTING_KEY_TO_TYPE.get(routing_key, routing_key)

        entity = ViolationEntity(
            id=uuid.uuid4(),
            enterprise_id=UUID(body["enterprise_id"]),
            zone_id=UUID(body["zone_id"]),
            camera_id=UUID(body["camera_id"]),
            violation_type=violation_type,
            confidence=float(body.get("confidence", 0.0)),
            snapshot_key=body.get("snapshot_key"),
            track_id=body.get("track_id"),
            shift_id=UUID(body["shift_id"]) if body.get("shift_id") else None,
            rule_id=UUID(body["rule_id"]) if body.get("rule_id") else None,
            is_false_positive=False,
            fp_reason=None,
            needs_review=float(body.get("confidence", 0.0)) < 0.60,
            created_on=datetime.now(timezone.utc),
        )
        saved = await self._repo.create(entity)
        log.info(
            "ppe.violation_saved",
            violation_id=str(saved.id),
            type=violation_type,
            confidence=entity.confidence,
            needs_review=entity.needs_review,
        )
        return saved

    # ── API ────────────────────────────────────────────────────────────────

    async def list_violations(
        self,
        enterprise_id: UUID,
        zone_id: UUID | None = None,
        camera_id: UUID | None = None,
        violation_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        items, total = await self._repo.list(
            enterprise_id, zone_id, camera_id, violation_type,
            from_dt, to_dt, None, page, page_size,
        )
        return [await self.enrich(v) for v in items], total

    async def get_violation(self, violation_id: UUID, enterprise_id: UUID) -> dict:
        v = await self._repo.get_by_id(violation_id, enterprise_id)
        if not v:
            raise NotFoundException("Violation", str(violation_id))
        return await self.enrich(v)

    async def enrich(self, v: ViolationEntity) -> dict:
        snapshot_url = None
        if v.snapshot_key:
            try:
                snapshot_url = get_presigned_url("snapshots", v.snapshot_key)
            except Exception as e:
                log.warning("ppe.presigned_url_failed", snapshot_key=v.snapshot_key, error=str(e))
        return {
            "id": str(v.id),
            "enterprise_id": str(v.enterprise_id),
            "zone_id": str(v.zone_id),
            "camera_id": str(v.camera_id),
            "violation_type": v.violation_type,
            "confidence": v.confidence,
            "snapshot_url": snapshot_url,
            "track_id": v.track_id,
            "shift_id": str(v.shift_id) if v.shift_id else None,
            "is_false_positive": v.is_false_positive,
            "needs_review": v.needs_review,
            "created_on": v.created_on.isoformat(),
        }
