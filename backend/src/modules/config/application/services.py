"""
ConfigService — zone detection config read/update with version increment,
history trail, and hot-push to AI workers via RabbitMQ (rule #8).
"""
import uuid
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.shared.database.models import ConfigHistory, ZoneConfig
from src.shared.messaging.publisher import publish_config_event

log = structlog.get_logger()

_CONFIG_FIELDS = (
    "person_threshold", "helmet_threshold", "vest_threshold", "gloves_threshold",
    "shoes_threshold", "mask_threshold", "max_occupancy", "frame_sample_fps",
    "ppe_required", "cooldown_seconds", "required_consecutive_frames",
    "low_confidence_floor",
)


class ConfigService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_zone_config(self, zone_id: UUID, enterprise_id: UUID) -> dict:
        config = await self._get_row(zone_id, enterprise_id)
        return self.to_dict(config)

    async def update_zone_config(
        self,
        zone_id: UUID,
        enterprise_id: UUID,
        changes: dict,
        changed_by: UUID,
        change_reason: str | None = None,
    ) -> dict:
        config = await self._get_row(zone_id, enterprise_id)
        old = self.to_dict(config)

        applied = {k: v for k, v in changes.items() if k in _CONFIG_FIELDS and v is not None}
        for field, value in applied.items():
            setattr(config, field, value)

        # CRITICAL (master context Section 6): version increments on every
        # save — AI workers discard config events with version <= local.
        config.version = (config.version or 1) + 1
        config.updated_by = changed_by
        config.updated_at = datetime.now(timezone.utc)

        new = self.to_dict(config)
        self._db.add(ConfigHistory(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            zone_id=zone_id,
            changed_by=changed_by,
            old_config=old,
            new_config=new,
            change_reason=change_reason,
        ))
        await self._db.commit()

        from src.modules.audit.application.services import AuditService
        await AuditService(self._db).record(
            enterprise_id=enterprise_id,
            user_id=changed_by,
            action="ZONE_CONFIG_UPDATED",
            entity_type="zone_config",
            entity_id=zone_id,
            old_value=old,
            new_value=new,
        )

        # Hot-push to AI workers — no restart needed (rule #8)
        await publish_config_event("config.zone_config_updated", {
            "event": "zone_config_updated",
            "enterprise_id": str(enterprise_id),
            "zone_id": str(zone_id),
            "config": new,
        })
        log.info("config.zone_updated", zone_id=str(zone_id), version=new["version"],
                 fields=list(applied))
        return new

    async def get_history(self, zone_id: UUID, enterprise_id: UUID, limit: int = 50) -> list[dict]:
        rows = (await self._db.execute(
            select(ConfigHistory)
            .where(
                ConfigHistory.zone_id == zone_id,
                ConfigHistory.enterprise_id == enterprise_id,
            )
            .order_by(ConfigHistory.changed_at.desc())
            .limit(limit)
        )).scalars()
        return [
            {
                "id": str(h.id),
                "zone_id": str(h.zone_id),
                "changed_by": str(h.changed_by) if h.changed_by else None,
                "old_config": h.old_config,
                "new_config": h.new_config,
                "change_reason": h.change_reason,
                "changed_at": h.changed_at.isoformat(),
            }
            for h in rows
        ]

    async def restore(
        self, zone_id: UUID, enterprise_id: UUID, history_id: UUID, changed_by: UUID
    ) -> dict:
        entry = (await self._db.execute(
            select(ConfigHistory).where(
                ConfigHistory.id == history_id,
                ConfigHistory.zone_id == zone_id,
                ConfigHistory.enterprise_id == enterprise_id,
            )
        )).scalar_one_or_none()
        if not entry:
            raise NotFoundException("ConfigHistory", str(history_id))

        snapshot = {k: v for k, v in (entry.old_config or {}).items() if k in _CONFIG_FIELDS}
        return await self.update_zone_config(
            zone_id, enterprise_id, snapshot, changed_by,
            change_reason=f"Restored from history {history_id}",
        )

    async def _get_row(self, zone_id: UUID, enterprise_id: UUID) -> ZoneConfig:
        config = (await self._db.execute(
            select(ZoneConfig).where(
                ZoneConfig.zone_id == zone_id,
                ZoneConfig.enterprise_id == enterprise_id,
            )
        )).scalar_one_or_none()
        if not config:
            raise NotFoundException("ZoneConfig", str(zone_id))
        return config

    @staticmethod
    def to_dict(c: ZoneConfig) -> dict:
        return {
            "id": str(c.id),
            "zone_id": str(c.zone_id),
            "person_threshold": c.person_threshold,
            "helmet_threshold": c.helmet_threshold,
            "vest_threshold": c.vest_threshold,
            "gloves_threshold": c.gloves_threshold,
            "shoes_threshold": c.shoes_threshold,
            "mask_threshold": c.mask_threshold,
            "max_occupancy": c.max_occupancy,
            "frame_sample_fps": c.frame_sample_fps,
            "ppe_required": c.ppe_required,
            "cooldown_seconds": c.cooldown_seconds,
            "required_consecutive_frames": c.required_consecutive_frames,
            "low_confidence_floor": c.low_confidence_floor,
            "updated_by": str(c.updated_by) if c.updated_by else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "version": c.version,
        }
