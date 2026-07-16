"""
ZoneService — read-only listing for pickers (e.g. the Add Camera form) plus
full CRUD. Every new zone gets a matching config.zone_configs row created
in the same transaction, so AI workers always find one (master context
Section 6 — zone_configs is effectively required, not optional).
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.modules.zone.domain.entities import ZoneEntity
from src.modules.zone.infrastructure.repositories import ZoneRepository
from src.shared.database.models import Department, Enterprise, Factory, Zone, ZoneConfig
from src.shared.database.pid import to_pk, to_public_id
from src.shared.security.scope import ScopeFilter, apply_zone_scope

log = structlog.get_logger()


class ZoneService:

    def __init__(self, repo: ZoneRepository, db: AsyncSession):
        self._repo = repo
        self._db = db

    # ── Picker listing (existing) ───────────────────────────────────────────

    async def list_zones(
        self, enterprise_id: str, factory_id: str | None = None, scope: ScopeFilter | None = None
    ) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = (
            select(Zone, Factory.name, Factory.public_id, Department.name, Department.public_id, ZoneConfig)
            .join(Factory, Factory.id == Zone.factory_id)
            .join(Department, Department.id == Zone.department_id)
            .outerjoin(ZoneConfig, ZoneConfig.zone_id == Zone.id)
            .where(
                Zone.enterprise_id == ent_pk,
                Zone.deleted_at.is_(None),
                Zone.status == "Active",
            )
            .order_by(Factory.name, Zone.name)
        )
        if factory_id:
            q = q.where(Zone.factory_id == await to_pk(self._db, Factory, factory_id))
        if scope is not None:
            q = await apply_zone_scope(self._db, q, scope, Zone.factory_id, Zone.id)

        rows = (await self._db.execute(q)).all()
        return [
            {
                "id": zone.public_id,
                "name": zone.name,
                "code": zone.code,
                "zone_type": zone.zone_type,
                "is_restricted": zone.is_restricted,
                "max_occupancy": zone.max_occupancy,
                "factory_id": factory_public_id,
                "factory_name": factory_name,
                "department_id": department_public_id,
                "department_name": department_name,
                "required_ppe_types": config.required_ppe_types if config else ["helmet", "vest"],
            }
            for zone, factory_name, factory_public_id, department_name, department_public_id, config in rows
        ]

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def get_zone(
        self, zone_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> ZoneEntity:
        zone = await self._repo.get_by_id(zone_id, enterprise_id, scope)
        if not zone:
            raise NotFoundException("Zone", str(zone_id))
        return zone

    async def create_zone(
        self,
        enterprise_id: str,
        department_id: str,
        name: str,
        code: str,
        max_occupancy: int,
        zone_type: str = "Production",
        is_restricted: bool = False,
        supervisor_id: str | None = None,
        required_ppe_types: list[str] | None = None,
    ) -> ZoneEntity:
        # factory_id is derived from the department, never taken from the
        # caller — a zone's factory must always match its department's, so
        # there's no independent value to trust or cross-validate here.
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        department = (await self._db.execute(
            select(Department).where(
                Department.public_id == department_id, Department.enterprise_id == ent_pk,
            )
        )).scalar_one_or_none()
        if not department:
            raise NotFoundException("Department", str(department_id))

        factory_public_id = await to_public_id(self._db, Factory, department.factory_id)

        entity = ZoneEntity(
            enterprise_id=enterprise_id,
            factory_id=factory_public_id,
            department_id=department_id,
            name=name,
            code=code,
            max_occupancy=max_occupancy,
            zone_type=zone_type,
            is_restricted=is_restricted,
            supervisor_id=supervisor_id,
        )
        zone = await self._repo.create(entity)

        zone_pk = await to_pk(self._db, Zone, zone.id)
        self._db.add(ZoneConfig(
            enterprise_id=ent_pk,
            zone_id=zone_pk,
            max_occupancy=max_occupancy,
            required_ppe_types=required_ppe_types if required_ppe_types is not None else ["helmet", "vest"],
        ))
        await self._db.commit()

        log.info("zone.created", zone_id=str(zone.id), name=name)
        return zone

    async def update_zone(
        self, zone_id: str, enterprise_id: str, scope: ScopeFilter | None = None, **fields,
    ) -> ZoneEntity:
        zone = await self.get_zone(zone_id, enterprise_id, scope)
        for key, val in fields.items():
            if val is not None and hasattr(zone, key):
                setattr(zone, key, val)
        return await self._repo.update(zone)

    async def delete_zone(
        self, zone_id: str, enterprise_id: str, scope: ScopeFilter | None = None,
    ) -> None:
        await self.get_zone(zone_id, enterprise_id, scope)
        await self._repo.delete(zone_id, enterprise_id)
        log.info("zone.deleted", zone_id=str(zone_id))

    @staticmethod
    def to_dict(z: ZoneEntity) -> dict:
        return {
            "id": z.id,
            "enterprise_id": z.enterprise_id,
            "factory_id": z.factory_id,
            "department_id": z.department_id,
            "name": z.name,
            "code": z.code,
            "max_occupancy": z.max_occupancy,
            "zone_type": z.zone_type,
            "is_restricted": z.is_restricted,
            "supervisor_id": z.supervisor_id,
            "status": z.status,
            "created_at": z.created_at.isoformat() if z.created_at else None,
            "updated_at": z.updated_at.isoformat() if z.updated_at else None,
        }
