"""
MaintenanceService — scheduled camera maintenance records + live maintenance
mode. While a camera is in maintenance mode the backend consumer suppresses
alert creation for its events (master context: "Alert during maintenance" is
an explicit mistake to avoid). Violations are still recorded for the audit
trail — only alerting/notification is silenced.
"""
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.shared.database.models import Camera, CameraMaintenance, Enterprise, User
from src.shared.database.pid import to_pk, to_public_id

log = structlog.get_logger()


class MaintenanceService:

    def __init__(self, db: AsyncSession):
        self._db = db

    # ── Scheduled maintenance records ───────────────────────────────────────

    async def list(self, enterprise_id: str, camera_id: str | None = None, status: str | None = None) -> list[dict]:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        q = select(CameraMaintenance).where(CameraMaintenance.enterprise_id == ent_pk)
        if camera_id:
            q = q.where(CameraMaintenance.camera_id == await to_pk(self._db, Camera, camera_id))
        if status:
            q = q.where(CameraMaintenance.status == status)
        rows = (await self._db.execute(q.order_by(CameraMaintenance.scheduled_date.desc()))).scalars()
        return [await self.to_dict(self._db, m) for m in rows]

    async def schedule(
        self,
        enterprise_id: str,
        camera_id: str,
        scheduled_date: date,
        maintenance_type: str,
        assigned_to: str | None,
        notes: str | None,
    ) -> dict:
        camera = await self._get_camera(camera_id, enterprise_id)
        row = CameraMaintenance(
            enterprise_id=camera.enterprise_id,
            camera_id=camera.id,
            scheduled_date=scheduled_date,
            maintenance_type=maintenance_type,
            assigned_to=await to_pk(self._db, User, assigned_to),
            status="Scheduled",
            notes=notes,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("maintenance.scheduled", camera_id=str(camera_id), date=str(scheduled_date))
        return await self.to_dict(self._db, row)

    async def complete(
        self,
        maintenance_id: str,
        enterprise_id: str,
        completed_by: str,
        completion_notes: str | None,
        next_due_date: date | None,
    ) -> dict:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        row = (await self._db.execute(
            select(CameraMaintenance).where(
                CameraMaintenance.public_id == maintenance_id,
                CameraMaintenance.enterprise_id == ent_pk,
            )
        )).scalar_one_or_none()
        if not row:
            raise NotFoundException("Maintenance", str(maintenance_id))

        row.status = "Completed"
        row.completed_at = datetime.now(timezone.utc)
        row.completed_by = await to_pk(self._db, User, completed_by)
        row.completion_notes = completion_notes
        row.next_due_date = next_due_date
        await self._db.commit()
        await self._db.refresh(row)
        return await self.to_dict(self._db, row)

    # ── Live maintenance mode (alert suppression) ───────────────────────────

    async def enable_mode(self, camera_id: str, enterprise_id: str, until: datetime | None) -> dict:
        camera = await self._get_camera(camera_id, enterprise_id)
        camera.in_maintenance = True
        camera.maintenance_until = until
        await self._db.commit()
        log.info("maintenance.mode_enabled", camera_id=str(camera_id), until=str(until))
        return {"camera_id": camera_id, "in_maintenance": True,
                "maintenance_until": until.isoformat() if until else None}

    async def disable_mode(self, camera_id: str, enterprise_id: str) -> dict:
        camera = await self._get_camera(camera_id, enterprise_id)
        camera.in_maintenance = False
        camera.maintenance_until = None
        await self._db.commit()
        log.info("maintenance.mode_disabled", camera_id=str(camera_id))
        return {"camera_id": camera_id, "in_maintenance": False, "maintenance_until": None}

    @staticmethod
    async def is_in_maintenance(db: AsyncSession, camera_id: str) -> bool:
        """Called by the event consumer before creating alerts. A camera whose
        maintenance_until has passed is treated as active again."""
        camera = (await db.execute(
            select(Camera).where(Camera.public_id == camera_id)
        )).scalar_one_or_none()
        if not camera or not camera.in_maintenance:
            return False
        if camera.maintenance_until and camera.maintenance_until < datetime.now(timezone.utc):
            return False
        return True

    async def _get_camera(self, camera_id: str, enterprise_id: str) -> Camera:
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        camera = (await self._db.execute(
            select(Camera).where(Camera.public_id == camera_id, Camera.enterprise_id == ent_pk)
        )).scalar_one_or_none()
        if not camera:
            raise NotFoundException("Camera", str(camera_id))
        return camera

    @staticmethod
    async def to_dict(db: AsyncSession, m: CameraMaintenance) -> dict:
        return {
            "id": m.public_id,
            "camera_id": await to_public_id(db, Camera, m.camera_id),
            "scheduled_date": m.scheduled_date.isoformat() if m.scheduled_date else None,
            "maintenance_type": m.maintenance_type,
            "assigned_to": await to_public_id(db, User, m.assigned_to),
            "status": m.status,
            "notes": m.notes,
            "completed_at": m.completed_at.isoformat() if m.completed_at else None,
            "completed_by": await to_public_id(db, User, m.completed_by),
            "completion_notes": m.completion_notes,
            "next_due_date": m.next_due_date.isoformat() if m.next_due_date else None,
        }
