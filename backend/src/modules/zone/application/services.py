"""
ZoneService — read-only listing for pickers (e.g. the Add Camera form) plus
full CRUD. Every new zone gets a matching config.zone_configs row created
in the same transaction, so AI workers always find one (master context
Section 6 — zone_configs is effectively required, not optional).
"""
import uuid
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.modules.zone.domain.entities import ZoneEntity
from src.modules.zone.infrastructure.repositories import ZoneRepository
from src.shared.database.models import Department, Factory, Zone, ZoneConfig

log = structlog.get_logger()


class ZoneService:

    def __init__(self, repo: ZoneRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    # ── Picker listing (existing) ───────────────────────────────────────────

    async def list_zones(self, enterprise_id: UUID, factory_id: UUID | None = None) -> list[dict]:
        q = (
            select(Zone, Factory.name, Department.name)
            .join(Factory, Factory.id == Zone.factory_id)
            .join(Department, Department.id == Zone.department_id)
            .where(
                Zone.enterprise_id == enterprise_id,
                Zone.deleted_at.is_(None),
                Zone.status == "Active",
            )
            .order_by(Factory.name, Zone.name)
        )
        if factory_id:
            q = q.where(Zone.factory_id == factory_id)

        rows = (await self._db.execute(q)).all()
        return [
            {
                "id": str(zone.id),
                "name": zone.name,
                "code": zone.code,
                "zone_type": zone.zone_type,
                "is_restricted": zone.is_restricted,
                "max_occupancy": zone.max_occupancy,
                "factory_id": str(zone.factory_id),
                "factory_name": factory_name,
                "department_id": str(zone.department_id),
                "department_name": department_name,
            }
            for zone, factory_name, department_name in rows
        ]

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def get_zone(self, zone_id: UUID, enterprise_id: UUID) -> ZoneEntity:
        zone = await self._repo.get_by_id(zone_id, enterprise_id)
        if not zone:
            raise NotFoundException("Zone", str(zone_id))
        return zone

    async def create_zone(
        self,
        enterprise_id: UUID,
        factory_id: UUID,
        department_id: UUID,
        name: str,
        code: str,
        max_occupancy: int,
        zone_type: str = "Production",
        is_restricted: bool = False,
        supervisor_id: UUID | None = None,
        ppe_required: list[str] | None = None,
    ) -> ZoneEntity:
        entity = ZoneEntity(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            factory_id=factory_id,
            department_id=department_id,
            name=name,
            code=code,
            max_occupancy=max_occupancy,
            zone_type=zone_type,
            is_restricted=is_restricted,
            supervisor_id=supervisor_id,
        )
        zone = await self._repo.create(entity)

        self._db.add(ZoneConfig(
            id=uuid.uuid4(),
            enterprise_id=enterprise_id,
            zone_id=zone.id,
            max_occupancy=max_occupancy,
            ppe_required=ppe_required or ["helmet", "vest"],
        ))
        await self._db.commit()

        log.info("zone.created", zone_id=str(zone.id), name=name)
        return zone

    async def update_zone(self, zone_id: UUID, enterprise_id: UUID, **fields) -> ZoneEntity:
        zone = await self.get_zone(zone_id, enterprise_id)
        for key, val in fields.items():
            if val is not None and hasattr(zone, key):
                setattr(zone, key, val)
        return await self._repo.update(zone)

    async def delete_zone(self, zone_id: UUID, enterprise_id: UUID) -> None:
        await self.get_zone(zone_id, enterprise_id)
        await self._repo.delete(zone_id, enterprise_id)
        log.info("zone.deleted", zone_id=str(zone_id))

    @staticmethod
    def to_dict(z: ZoneEntity) -> dict:
        return {
            "id": str(z.id),
            "enterprise_id": str(z.enterprise_id),
            "factory_id": str(z.factory_id),
            "department_id": str(z.department_id),
            "name": z.name,
            "code": z.code,
            "max_occupancy": z.max_occupancy,
            "zone_type": z.zone_type,
            "is_restricted": z.is_restricted,
            "supervisor_id": str(z.supervisor_id) if z.supervisor_id else None,
            "status": z.status,
            "created_on": z.created_on.isoformat() if z.created_on else None,
            "modified_on": z.modified_on.isoformat() if z.modified_on else None,
        }
