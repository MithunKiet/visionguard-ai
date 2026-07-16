"""
OccupancyService — persist occupancy readings from RabbitMQ events, serve
current + historical occupancy queries.
"""
from datetime import datetime, timezone

import structlog

from src.modules.occupancy.domain.entities import OccupancyLogEntity
from src.modules.occupancy.infrastructure.repositories import OccupancyRepository
from src.shared.security.scope import ScopeFilter

log = structlog.get_logger()


class OccupancyService:

    def __init__(self, repo: OccupancyRepository):
        self._repo = repo

    # ── Called by RabbitMQ consumer ────────────────────────────────────────

    async def handle_occupancy_event(self, body: dict) -> OccupancyLogEntity:
        entity = OccupancyLogEntity(
            enterprise_id=body["enterprise_id"],
            zone_id=body["zone_id"],
            camera_id=body["camera_id"],
            current_count=int(body.get("count", 0)),
            shift_id=body.get("shift_id"),
            timestamp=datetime.now(timezone.utc),
        )
        saved = await self._repo.create(entity)
        log.debug("occupancy.logged", zone_id=str(entity.zone_id), count=entity.current_count)
        return saved

    # ── API ────────────────────────────────────────────────────────────────

    async def current(self, enterprise_id: str, scope: ScopeFilter | None = None) -> list[dict]:
        return await self._repo.current_per_zone(enterprise_id, scope)

    async def history(
        self,
        enterprise_id: str,
        zone_id: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
        scope: ScopeFilter | None = None,
    ) -> tuple[list[dict], int]:
        items, total = await self._repo.history(
            enterprise_id, zone_id, from_dt, to_dt, page, page_size, scope
        )
        return [self.to_dict(o) for o in items], total

    @staticmethod
    def to_dict(o: OccupancyLogEntity) -> dict:
        return {
            "id": o.id,
            "zone_id": o.zone_id,
            "camera_id": o.camera_id,
            "current_count": o.current_count,
            "shift_id": o.shift_id,
            "timestamp": o.timestamp.isoformat(),
        }
