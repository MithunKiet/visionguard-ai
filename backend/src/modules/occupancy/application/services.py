"""
OccupancyService — persist occupancy readings from RabbitMQ events, serve
current + historical occupancy queries.
"""
import uuid
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.modules.occupancy.domain.entities import OccupancyLogEntity
from src.modules.occupancy.infrastructure.repositories import OccupancyRepository

log = structlog.get_logger()


class OccupancyService:

    def __init__(self, repo: OccupancyRepository):
        self._repo = repo

    # ── Called by RabbitMQ consumer ────────────────────────────────────────

    async def handle_occupancy_event(self, body: dict) -> OccupancyLogEntity:
        entity = OccupancyLogEntity(
            id=uuid.uuid4(),
            enterprise_id=UUID(body["enterprise_id"]),
            zone_id=UUID(body["zone_id"]),
            camera_id=UUID(body["camera_id"]),
            current_count=int(body.get("count", 0)),
            shift_id=UUID(body["shift_id"]) if body.get("shift_id") else None,
            timestamp=datetime.now(timezone.utc),
        )
        saved = await self._repo.create(entity)
        log.debug("occupancy.logged", zone_id=str(entity.zone_id), count=entity.current_count)
        return saved

    # ── API ────────────────────────────────────────────────────────────────

    async def current(self, enterprise_id: UUID) -> list[dict]:
        return await self._repo.current_per_zone(enterprise_id)

    async def history(
        self,
        enterprise_id: UUID,
        zone_id: UUID | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        items, total = await self._repo.history(
            enterprise_id, zone_id, from_dt, to_dt, page, page_size
        )
        return [self.to_dict(o) for o in items], total

    @staticmethod
    def to_dict(o: OccupancyLogEntity) -> dict:
        return {
            "id": str(o.id),
            "zone_id": str(o.zone_id),
            "camera_id": str(o.camera_id),
            "current_count": o.current_count,
            "shift_id": str(o.shift_id) if o.shift_id else None,
            "timestamp": o.timestamp.isoformat(),
        }
