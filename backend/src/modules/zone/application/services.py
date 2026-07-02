"""
ZoneService — read-only zone listing for pickers (e.g. the Add Camera form).
Returns each zone with its factory/department names embedded so the frontend
needs a single call to render a grouped dropdown.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database.models import Department, Factory, Zone


class ZoneService:

    def __init__(self, db: AsyncSession):
        self._db = db

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
