"""
SetupWizardService — 4-step first-time onboarding (master context Section 14):
Factory → Department → Zone (+ PPE config) → Camera → Complete.

Progress is persisted after every step, so an admin who closes the browser
resumes exactly where they left off. Steps must run in order; each step
requires the previous one's entity to exist in the saved progress.
"""
import uuid
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import VisionGuardException
from src.shared.database.models import (
    AIWorker,
    Camera,
    Department,
    Factory,
    SetupProgress,
    User,
    Zone,
    ZoneConfig,
)

log = structlog.get_logger()


class SetupWizardService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_progress(self, user_id: UUID, enterprise_id: UUID) -> dict:
        progress = await self._get_or_create(user_id, enterprise_id)
        return self.to_dict(progress)

    async def create_factory(
        self, user_id: UUID, enterprise_id: UUID, name: str, code: str, location: str | None
    ) -> dict:
        progress = await self._get_or_create(user_id, enterprise_id)
        factory = Factory(
            id=uuid.uuid4(), enterprise_id=enterprise_id,
            name=name, code=code, location=location,
        )
        self._db.add(factory)
        progress.factory_id = factory.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 1)
        await self._db.commit()
        log.info("setup.factory_created", factory_id=str(factory.id))
        return {"factory_id": str(factory.id), **self.to_dict(progress)}

    async def create_department(
        self, user_id: UUID, enterprise_id: UUID, name: str, code: str
    ) -> dict:
        progress = await self._require_step(user_id, enterprise_id, 1, "factory")
        department = Department(
            id=uuid.uuid4(), enterprise_id=enterprise_id,
            factory_id=progress.factory_id, name=name, code=code,
        )
        self._db.add(department)
        progress.department_id = department.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 2)
        await self._db.commit()
        log.info("setup.department_created", department_id=str(department.id))
        return {"department_id": str(department.id), **self.to_dict(progress)}

    async def create_zone(
        self,
        user_id: UUID,
        enterprise_id: UUID,
        name: str,
        code: str,
        max_occupancy: int,
        zone_type: str,
        is_restricted: bool,
        ppe_required: list[str],
    ) -> dict:
        progress = await self._require_step(user_id, enterprise_id, 2, "department")
        zone = Zone(
            id=uuid.uuid4(), enterprise_id=enterprise_id,
            factory_id=progress.factory_id, department_id=progress.department_id,
            name=name, code=code, max_occupancy=max_occupancy,
            zone_type=zone_type, is_restricted=is_restricted,
        )
        self._db.add(zone)
        # Every zone gets a config row immediately so AI workers always find one
        self._db.add(ZoneConfig(
            id=uuid.uuid4(), enterprise_id=enterprise_id, zone_id=zone.id,
            max_occupancy=max_occupancy, ppe_required=ppe_required,
        ))
        progress.zone_id = zone.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 3)
        await self._db.commit()
        log.info("setup.zone_created", zone_id=str(zone.id))
        return {"zone_id": str(zone.id), **self.to_dict(progress)}

    async def create_camera(
        self,
        user_id: UUID,
        enterprise_id: UUID,
        name: str,
        code: str,
        rtsp_url: str,
        camera_type: str,
        position_desc: str | None,
        placement_confirmed: bool,
    ) -> dict:
        if not placement_confirmed:
            raise VisionGuardException(
                code="PLACEMENT_NOT_CONFIRMED",
                message="Confirm the camera placement checklist before adding the camera",
                status_code=422,
            )
        progress = await self._require_step(user_id, enterprise_id, 3, "zone")

        # Auto-assign to the first live worker of this enterprise, if any
        worker = (await self._db.execute(
            select(AIWorker).where(AIWorker.enterprise_id == enterprise_id).limit(1)
        )).scalar_one_or_none()

        camera = Camera(
            id=uuid.uuid4(), enterprise_id=enterprise_id,
            factory_id=progress.factory_id, zone_id=progress.zone_id,
            worker_id=worker.id if worker else None,
            name=name, code=code, rtsp_url=rtsp_url,
            camera_type=camera_type, position_desc=position_desc,
        )
        self._db.add(camera)
        progress.camera_id = camera.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 4)
        await self._db.commit()
        log.info("setup.camera_created", camera_id=str(camera.id),
                 assigned_worker=str(worker.id) if worker else None)
        return {"camera_id": str(camera.id), **self.to_dict(progress)}

    async def complete(self, user_id: UUID, enterprise_id: UUID) -> dict:
        progress = await self._require_step(user_id, enterprise_id, 4, "camera")
        progress.completed_at = datetime.now(timezone.utc)

        user = (await self._db.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user:
            user.setup_completed = True

        await self._db.commit()
        log.info("setup.completed", user_id=str(user_id))
        return self.to_dict(progress)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _get_or_create(self, user_id: UUID, enterprise_id: UUID) -> SetupProgress:
        progress = (await self._db.execute(
            select(SetupProgress).where(
                SetupProgress.user_id == user_id,
                SetupProgress.enterprise_id == enterprise_id,
            )
        )).scalar_one_or_none()
        if not progress:
            progress = SetupProgress(
                id=uuid.uuid4(), user_id=user_id, enterprise_id=enterprise_id,
                last_completed_step=0,
            )
            self._db.add(progress)
            await self._db.commit()
        return progress

    async def _require_step(
        self, user_id: UUID, enterprise_id: UUID, step: int, missing: str
    ) -> SetupProgress:
        progress = await self._get_or_create(user_id, enterprise_id)
        if (progress.last_completed_step or 0) < step:
            raise VisionGuardException(
                code="SETUP_STEP_ORDER",
                message=f"Complete the {missing} step first (currently at step "
                        f"{progress.last_completed_step or 0})",
                status_code=422,
            )
        return progress

    @staticmethod
    def to_dict(p: SetupProgress) -> dict:
        return {
            "last_completed_step": p.last_completed_step or 0,
            "factory_id": str(p.factory_id) if p.factory_id else None,
            "department_id": str(p.department_id) if p.department_id else None,
            "zone_id": str(p.zone_id) if p.zone_id else None,
            "camera_id": str(p.camera_id) if p.camera_id else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        }
