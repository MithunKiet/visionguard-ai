"""
PPEService — save violations from RabbitMQ events, serve API queries.
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.modules.ppe.domain.entities import ViolationEntity
from src.modules.ppe.infrastructure.repositories import ViolationRepository
from src.shared.security.scope import ScopeFilter
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

    def __init__(self, repo: ViolationRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    # ── Called by RabbitMQ consumer ────────────────────────────────────────

    async def handle_violation_event(self, routing_key: str, body: dict) -> ViolationEntity:
        violation_type = ROUTING_KEY_TO_TYPE.get(routing_key, routing_key)

        entity = ViolationEntity(
            enterprise_id=body["enterprise_id"],
            zone_id=body["zone_id"],
            camera_id=body["camera_id"],
            violation_type=violation_type,
            confidence=float(body.get("confidence", 0.0)),
            snapshot_key=body.get("snapshot_key"),
            track_id=body.get("track_id"),
            shift_id=body.get("shift_id"),
            rule_id=body.get("rule_id"),
            is_false_positive=False,
            fp_reason=None,
            needs_review=float(body.get("confidence", 0.0)) < 0.60,
            created_at=datetime.now(timezone.utc),
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
        enterprise_id: str,
        zone_id: str | None = None,
        camera_id: str | None = None,
        violation_type: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
        scope: ScopeFilter | None = None,
    ) -> tuple[list[dict], int]:
        items, total = await self._repo.list(
            enterprise_id, zone_id, camera_id, violation_type,
            from_dt, to_dt, None, page, page_size, scope,
        )
        return [self.enrich(v) for v in items], total

    async def get_violation(
        self, violation_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> dict:
        v = await self._repo.get_by_id(violation_id, enterprise_id, scope)
        if not v:
            raise NotFoundException("Violation", str(violation_id))
        return self.enrich(v)

    def enrich(self, v: ViolationEntity) -> dict:
        """Adds the presigned snapshot URL (not DB-bound) on top of the
        zone/camera display fields the repository's joined query already
        populated — no per-row DB queries here (see infrastructure/
        repositories.py's _JOINED_COLUMNS for why)."""
        snapshot_url = None
        if v.snapshot_key:
            try:
                snapshot_url = get_presigned_url("snapshots", v.snapshot_key)
            except Exception as e:
                log.warning("ppe.presigned_url_failed", snapshot_key=v.snapshot_key, error=str(e))

        return {
            "id": v.id,
            "enterprise_id": v.enterprise_id,
            "zone_id": v.zone_id,
            "zone_name": v.zone_name,
            "camera_id": v.camera_id,
            "camera_name": v.camera_name,
            "camera_code": v.camera_code,
            "violation_type": v.violation_type,
            "confidence": v.confidence,
            "snapshot_url": snapshot_url,
            "track_id": v.track_id,
            "shift_id": v.shift_id,
            "is_false_positive": v.is_false_positive,
            "needs_review": v.needs_review,
            "created_on": v.created_at.isoformat(),
        }
