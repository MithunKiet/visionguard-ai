"""
Seed a demo Factory -> Department -> Zone (+ ZoneConfig) -> Camera, and
pre-register the AI Worker row so the camera can be assigned to it before
the worker container ever sends its first heartbeat.

Run AFTER seed_super_admin.py (needs the Enterprise + SYSTEM_ADMIN's id).

Usage (run from backend/ directory):
    python -m scripts.seed_demo_pilot

Environment variables:
    SEED_ENTERPRISE_CODE   (default: "VGD" — must match seed_super_admin)
    SEED_WORKER_ID         (default: "worker-1")
    SEED_CAMERA_RTSP_URL   (default: "rtsp://mediamtx:8554/factory-cam-01")
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.settings import settings
from src.shared.database.models import (
    Enterprise, Factory, Department, Zone, ZoneConfig, Camera, AIWorker, Role, User, UserRole,
)
from src.shared.security.password import hash_password

ENTERPRISE_CODE = os.getenv("SEED_ENTERPRISE_CODE", "VGD")
WORKER_ID       = os.getenv("SEED_WORKER_ID", "worker-1")
CAMERA_RTSP_URL = os.getenv("SEED_CAMERA_RTSP_URL", "rtsp://mediamtx:8554/factory-cam-01")
DEMO_PASSWORD   = os.getenv("SEED_DEMO_PASSWORD", "Demo@1234")

# One demo user per role so each role's permissions can be exercised in
# isolation, plus one user holding two roles at once (FACTORY_MANAGER +
# SAFETY_OFFICER) to demonstrate that a user isn't limited to a single role.
# factory_id/department_id/assigned_zone_ids are set per-role to match what
# that role would realistically be scoped to.
_DEMO_USERS = [
    {"email": "enterprise.admin@visionguard.ai", "name": "Enterprise Admin", "roles": ["ENTERPRISE_ADMIN"]},
    {"email": "factory.manager@visionguard.ai", "name": "Factory Manager", "roles": ["FACTORY_MANAGER"], "scope": "factory"},
    {"email": "safety.officer@visionguard.ai", "name": "Safety Officer", "roles": ["SAFETY_OFFICER"], "scope": "factory"},
    {"email": "supervisor@visionguard.ai", "name": "Supervisor", "roles": ["SUPERVISOR"], "scope": "zone"},
    {"email": "viewer@visionguard.ai", "name": "Viewer", "roles": ["VIEWER"], "scope": "factory"},
    {"email": "multi.role@visionguard.ai", "name": "Multi Role Demo",
     "roles": ["FACTORY_MANAGER", "SAFETY_OFFICER"], "scope": "factory"},
]


async def seed() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        enterprise = (await db.execute(
            select(Enterprise).where(Enterprise.code == ENTERPRISE_CODE)
        )).scalar_one_or_none()
        if not enterprise:
            print(f"[seed] Enterprise '{ENTERPRISE_CODE}' not found — run seed_super_admin.py first.")
            return

        factory = (await db.execute(
            select(Factory).where(Factory.enterprise_id == enterprise.id, Factory.code == "F1")
        )).scalar_one_or_none()
        if not factory:
            factory = Factory(enterprise_id=enterprise.id,
                               name="Demo Factory", code="F1", location="Pilot Site")
            db.add(factory)
            await db.flush()
            print("[seed] Factory created: Demo Factory (F1)")

        department = (await db.execute(
            select(Department).where(Department.factory_id == factory.id, Department.code == "D1")
        )).scalar_one_or_none()
        if not department:
            department = Department(enterprise_id=enterprise.id,
                                     factory_id=factory.id, name="Shop Floor", code="D1")
            db.add(department)
            await db.flush()
            print("[seed] Department created: Shop Floor (D1)")

        zone = (await db.execute(
            select(Zone).where(Zone.factory_id == factory.id, Zone.code == "Z1")
        )).scalar_one_or_none()
        if not zone:
            zone = Zone(enterprise_id=enterprise.id, factory_id=factory.id,
                        department_id=department.id, name="Assembly Line 1", code="Z1",
                        max_occupancy=20, zone_type="Production")
            db.add(zone)
            await db.flush()
            print("[seed] Zone created: Assembly Line 1 (Z1)")

        zone_config = (await db.execute(
            select(ZoneConfig).where(ZoneConfig.zone_id == zone.id)
        )).scalar_one_or_none()
        if not zone_config:
            zone_config = ZoneConfig(enterprise_id=enterprise.id, zone_id=zone.id,
                                      required_ppe_types=["helmet", "vest"])
            db.add(zone_config)
            print("[seed] ZoneConfig created for Assembly Line 1 (helmet + vest required)")

        worker = (await db.execute(
            select(AIWorker).where(AIWorker.worker_id == WORKER_ID)
        )).scalar_one_or_none()
        if not worker:
            worker = AIWorker(enterprise_id=enterprise.id,
                               worker_id=WORKER_ID, status="Offline", gpu_available=False)
            db.add(worker)
            await db.flush()
            print(f"[seed] AIWorker pre-registered: {WORKER_ID} (will go Online on first heartbeat)")

        camera = (await db.execute(
            select(Camera).where(Camera.zone_id == zone.id, Camera.code == "CAM1")
        )).scalar_one_or_none()
        if not camera:
            camera = Camera(enterprise_id=enterprise.id, factory_id=factory.id,
                             zone_id=zone.id, worker_id=worker.id, name="Assembly Line 1 - Cam 1",
                             code="CAM1", rtsp_url=CAMERA_RTSP_URL, camera_type="Fixed",
                             status="Active", fps=2.0)
            db.add(camera)
            print(f"[seed] Camera created: CAM1 -> {CAMERA_RTSP_URL} (assigned to {WORKER_ID})")
        else:
            print("[seed] Camera CAM1 already exists")

        for spec in _DEMO_USERS:
            existing = (await db.execute(
                select(User).where(User.email == spec["email"])
            )).scalar_one_or_none()
            if existing:
                print(f"[seed] User already exists: {spec['email']} ({', '.join(spec['roles'])})")
                continue

            scope = spec.get("scope")
            new_user = User(
                
                enterprise_id=enterprise.id,
                name=spec["name"],
                email=spec["email"],
                password_hash=hash_password(DEMO_PASSWORD),
                status="Active",
                is_first_login=True,
                setup_completed=True,
                factory_id=factory.id if scope in ("factory", "zone") else None,
                department_id=department.id if scope == "zone" else None,
                assigned_zone_ids=[zone.public_id] if scope == "zone" else [],
            )
            db.add(new_user)
            await db.flush()
            for role_code in spec["roles"]:
                role = (await db.execute(select(Role).where(Role.code == role_code))).scalar_one()
                db.add(UserRole(user_public_id=new_user.public_id, role_public_id=role.public_id))
            print(f"[seed] User created: {spec['email']} ({', '.join(spec['roles'])})")

        await db.commit()
        print(f"[seed] Demo user password (all of the above): {DEMO_PASSWORD}")

    await engine.dispose()
    print(f"[seed] Enterprise ID: {enterprise.id}  <- set as ENTERPRISE_ID for the AI Worker")
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(seed())
