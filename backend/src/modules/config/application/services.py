"""
ConfigService — zone detection config read/update with version increment,
history trail, and hot-push to AI workers via RabbitMQ (rule #8).
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.shared.database.models import ConfigHistory, Enterprise, Zone, ZoneConfig
from src.shared.database.pid import to_pk, to_public_id
from src.shared.messaging.publisher import publish_config_event

log = structlog.get_logger()

_CONFIG_FIELDS = (
    "person_threshold", "helmet_threshold", "vest_threshold", "gloves_threshold",
    "shoes_threshold", "mask_threshold", "max_occupancy", "frame_sample_fps",
    "required_ppe_types", "cooldown_seconds", "required_consecutive_frames",
    "low_confidence_floor",
)


class ConfigService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_zone_config(self, zone_id: str, enterprise_id: str) -> dict:
        config = await self._get_row(zone_id, enterprise_id)
        return await self.to_dict(self._db, config)

    async def update_zone_config(
        self,
        zone_id: str,
        enterprise_id: str,
        changes: dict,
        changed_by: str,
        change_reason: str | None = None,
    ) -> dict:
        config = await self._get_row(zone_id, enterprise_id)
        old = await self.to_dict(self._db, config)

        applied = {k: v for k, v in changes.items() if k in _CONFIG_FIELDS and v is not None}
        for field, value in applied.items():
            setattr(config, field, value)

        # CRITICAL (master context Section 6): version increments on every
        # save — AI workers discard config events with version <= local.
        config.version = (config.version or 1) + 1
        config.updated_by = str(changed_by)
        config.updated_at = datetime.now(timezone.utc)

        new = await self.to_dict(self._db, config)
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        self._db.add(ConfigHistory(
            enterprise_id=ent_pk,
            zone_id=config.zone_id,
            created_by=str(changed_by),
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

    async def get_history(self, zone_id: str, enterprise_id: str, limit: int = 50) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        zone_pk = await to_pk(self._db, Zone, zone_id)
        rows = (await self._db.execute(
            select(ConfigHistory)
            .where(
                ConfigHistory.zone_id == zone_pk,
                ConfigHistory.enterprise_id == ent_pk,
            )
            .order_by(ConfigHistory.created_at.desc())
            .limit(limit)
        )).scalars()
        return [
            {
                "id": h.public_id,
                "zone_id": zone_id,
                "changed_by": h.created_by,
                "old_config": h.old_config,
                "new_config": h.new_config,
                "change_reason": h.change_reason,
                "created_at": h.created_at.isoformat(),
            }
            for h in rows
        ]

    async def restore(
        self, zone_id: str, enterprise_id: str, history_id: str, changed_by: str
    ) -> dict:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        zone_pk = await to_pk(self._db, Zone, zone_id)
        entry = (await self._db.execute(
            select(ConfigHistory).where(
                ConfigHistory.public_id == history_id,
                ConfigHistory.zone_id == zone_pk,
                ConfigHistory.enterprise_id == ent_pk,
            )
        )).scalar_one_or_none()
        if not entry:
            raise NotFoundException("ConfigHistory", str(history_id))

        snapshot = {k: v for k, v in (entry.old_config or {}).items() if k in _CONFIG_FIELDS}
        return await self.update_zone_config(
            zone_id, enterprise_id, snapshot, changed_by,
            change_reason=f"Restored from history {history_id}",
        )

    async def _get_row(self, zone_id: str, enterprise_id: str) -> ZoneConfig:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        zone_pk = await to_pk(self._db, Zone, zone_id)
        config = (await self._db.execute(
            select(ZoneConfig).where(
                ZoneConfig.zone_id == zone_pk,
                ZoneConfig.enterprise_id == ent_pk,
            )
        )).scalar_one_or_none()
        if not config:
            raise NotFoundException("ZoneConfig", str(zone_id))
        return config

    @staticmethod
    async def to_dict(db: AsyncSession, c: ZoneConfig) -> dict:
        return {
            "id": c.public_id,
            "zone_id": await to_public_id(db, Zone, c.zone_id),
            "person_threshold": c.person_threshold,
            "helmet_threshold": c.helmet_threshold,
            "vest_threshold": c.vest_threshold,
            "gloves_threshold": c.gloves_threshold,
            "shoes_threshold": c.shoes_threshold,
            "mask_threshold": c.mask_threshold,
            "max_occupancy": c.max_occupancy,
            "frame_sample_fps": c.frame_sample_fps,
            "required_ppe_types": c.required_ppe_types,
            "cooldown_seconds": c.cooldown_seconds,
            "required_consecutive_frames": c.required_consecutive_frames,
            "low_confidence_floor": c.low_confidence_floor,
            "updated_by": c.updated_by,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "version": c.version,
        }
