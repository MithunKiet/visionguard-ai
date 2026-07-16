"""
SetupWizardService — 4-step first-time onboarding (master context Section 14):
Factory -> Department -> Zone (+ PPE config) -> Camera -> Complete.

Progress is persisted after every step, so an admin who closes the browser
resumes exactly where they left off. Steps must run in order; each step
requires the previous one's entity to exist in the saved progress.
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import VisionGuardException
from src.shared.database.models import (
    AIWorker,
    Camera,
    Department,
    Enterprise,
    Factory,
    SetupProgress,
    User,
    Zone,
    ZoneConfig,
)
from src.shared.database.pid import to_pk, to_public_id

log = structlog.get_logger()


class SetupWizardService:

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_progress(self, user_id: str, enterprise_id: str) -> dict:
        progress = await self._get_or_create(user_id, enterprise_id)
        return await self.to_dict(self._db, progress)

    async def create_factory(
        self, user_id: str, enterprise_id: str, name: str, code: str, location: str | None
    ) -> dict:
        progress = await self._get_or_create(user_id, enterprise_id)
        factory = Factory(
            enterprise_id=progress.enterprise_id,
            name=name, code=code, location=location,
        )
        self._db.add(factory)
        await self._db.flush()
        progress.factory_id = factory.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 1)
        await self._db.commit()
        log.info("setup.factory_created", factory_id=str(factory.public_id))
        return {"factory_id": factory.public_id, **await self.to_dict(self._db, progress)}

    async def create_department(
        self, user_id: str, enterprise_id: str, name: str, code: str
    ) -> dict:
        progress = await self._require_step(user_id, enterprise_id, 1, "factory")
        department = Department(
            enterprise_id=progress.enterprise_id,
            factory_id=progress.factory_id, name=name, code=code,
        )
        self._db.add(department)
        await self._db.flush()
        progress.department_id = department.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 2)
        await self._db.commit()
        log.info("setup.department_created", department_id=str(department.public_id))
        return {"department_id": department.public_id, **await self.to_dict(self._db, progress)}

    async def create_zone(
        self,
        user_id: str,
        enterprise_id: str,
        name: str,
        code: str,
        max_occupancy: int,
        zone_type: str,
        is_restricted: bool,
        required_ppe_types: list[str] | None = None,
    ) -> dict:
        progress = await self._require_step(user_id, enterprise_id, 2, "department")
        zone = Zone(
            enterprise_id=progress.enterprise_id,
            factory_id=progress.factory_id, department_id=progress.department_id,
            name=name, code=code, max_occupancy=max_occupancy,
            zone_type=zone_type, is_restricted=is_restricted,
        )
        self._db.add(zone)
        await self._db.flush()
        # Every zone gets a config row immediately so AI workers always find one
        self._db.add(ZoneConfig(
            enterprise_id=progress.enterprise_id, zone_id=zone.id,
            max_occupancy=max_occupancy,
            required_ppe_types=required_ppe_types if required_ppe_types is not None else ["helmet", "vest"],
        ))
        progress.zone_id = zone.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 3)
        await self._db.commit()
        log.info("setup.zone_created", zone_id=str(zone.public_id))
        return {"zone_id": zone.public_id, **await self.to_dict(self._db, progress)}

    async def create_camera(
        self,
        user_id: str,
        enterprise_id: str,
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
            select(AIWorker).where(AIWorker.enterprise_id == progress.enterprise_id).limit(1)
        )).scalar_one_or_none()

        camera = Camera(
            enterprise_id=progress.enterprise_id,
            factory_id=progress.factory_id, zone_id=progress.zone_id,
            worker_id=worker.id if worker else None,
            name=name, code=code, rtsp_url=rtsp_url,
            camera_type=camera_type, position_desc=position_desc,
        )
        self._db.add(camera)
        await self._db.flush()
        progress.camera_id = camera.id
        progress.last_completed_step = max(progress.last_completed_step or 0, 4)
        await self._db.commit()
        log.info("setup.camera_created", camera_id=str(camera.public_id),
                 assigned_worker=str(worker.public_id) if worker else None)
        return {"camera_id": camera.public_id, **await self.to_dict(self._db, progress)}

    async def complete(self, user_id: str, enterprise_id: str) -> dict:
        progress = await self._require_step(user_id, enterprise_id, 4, "camera")
        progress.completed_at = datetime.now(timezone.utc)

        user = (await self._db.execute(
            select(User).where(User.id == progress.user_id)
        )).scalar_one_or_none()
        if user:
            user.setup_completed = True

        await self._db.commit()
        log.info("setup.completed", user_id=str(user_id))
        return await self.to_dict(self._db, progress)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _get_or_create(self, user_id: str, enterprise_id: str) -> SetupProgress:
        user_pk = await to_pk(self._db, User, user_id)
        ent_pk = await to_pk(self._db, Enterprise, enterprise_id)
        progress = (await self._db.execute(
            select(SetupProgress).where(
                SetupProgress.user_id == user_pk,
                SetupProgress.enterprise_id == ent_pk,
            )
        )).scalar_one_or_none()
        if not progress:
            progress = SetupProgress(
                user_id=user_pk, enterprise_id=ent_pk,
                last_completed_step=0,
            )
            self._db.add(progress)
            await self._db.commit()
        return progress

    async def _require_step(
        self, user_id: str, enterprise_id: str, step: int, missing: str
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
    async def to_dict(db: AsyncSession, p: SetupProgress) -> dict:
        return {
            "last_completed_step": p.last_completed_step or 0,
            "factory_id": await to_public_id(db, Factory, p.factory_id),
            "department_id": await to_public_id(db, Department, p.department_id),
            "zone_id": await to_public_id(db, Zone, p.zone_id),
            "camera_id": await to_public_id(db, Camera, p.camera_id),
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        }
