"""Real PostgreSQL concurrency, locality and API authorization regressions."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update

from src.core.exceptions import NotFoundException, VisionGuardException
from src.modules.camera.application.services import CameraService
from src.modules.camera.infrastructure.repositories import CameraRepository
from src.modules.worker.application.services import WorkerService
from src.modules.worker.infrastructure.repositories import WorkerRepository
from src.modules.worker.infrastructure.scheduling import WorkerSchedulingRepository
from src.shared.database.models import AIWorker, Camera, Department, Enterprise, Factory, Zone, ZoneConfig
from src.shared.database.session import AsyncSessionFactory, engine
from tests.test_review_integration import headers, setup as setup

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL")


@pytest.fixture
async def site():
    async with AsyncSessionFactory() as db:
        enterprise = Enterprise(name="Scheduling tenant", code=uuid4().hex)
        other = Enterprise(name="Other scheduling tenant", code=uuid4().hex)
        db.add_all([enterprise, other])
        await db.flush()
        places = []
        for ent in (enterprise, enterprise, other):
            factory = Factory(enterprise_id=ent.id, name="Factory", code=uuid4().hex)
            db.add(factory)
            await db.flush()
            dept = Department(enterprise_id=ent.id, factory_id=factory.id, name="Dept", code=uuid4().hex)
            db.add(dept)
            await db.flush()
            zone = Zone(enterprise_id=ent.id, factory_id=factory.id, department_id=dept.id,
                        name="Zone", code=uuid4().hex, max_occupancy=10)
            db.add(zone)
            await db.flush()
            db.add(ZoneConfig(enterprise_id=ent.id, zone_id=zone.id))
            worker = AIWorker(enterprise_id=ent.id, factory_id=factory.id, max_cameras=1,
                              worker_id=uuid4().hex, status="Online", last_heartbeat=datetime.now(timezone.utc))
            db.add(worker)
            await db.flush()
            places.append(SimpleNamespace(factory=factory, zone=zone, worker=worker))
        await db.commit()
    yield SimpleNamespace(enterprise=enterprise, other=other, places=places)
    await engine.dispose()


async def add_cameras(site, count=1, place=0, worker=None, status="Active"):
    p = site.places[place]
    async with AsyncSessionFactory() as db:
        cameras = [Camera(enterprise_id=p.factory.enterprise_id, factory_id=p.factory.id,
                          zone_id=p.zone.id, name="Camera", code=uuid4().hex,
                          rtsp_url="rtsp://camera.example.invalid/feed", worker_id=worker, status=status)
                   for _ in range(count)]
        db.add_all(cameras)
        await db.commit()
        return cameras


async def admit(site, camera):
    async with AsyncSessionFactory() as db:
        return await WorkerSchedulingRepository(db).admit_pending(site.enterprise.public_id, camera_id=camera.public_id)


async def test_factory_locality_capacity_and_inactive_assignments(site):
    own, other_factory, _ = site.places
    existing = (await add_cameras(site, worker=own.worker.id, status="Inactive"))[0]
    pending = (await add_cameras(site))[0]
    assert await admit(site, pending) == {}  # The empty remote factory is not eligible.
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(Camera).where(Camera.worker_id == other_factory.worker.id)) == 0
        await db.execute(update(Camera).where(Camera.id == existing.id).values(deleted_at=datetime.now(timezone.utc)))
        await db.commit()
    assert await admit(site, pending) == {pending.public_id: own.worker.public_id}


async def test_last_slot_cannot_be_oversubscribed_across_concurrent_sessions(site):
    cameras = await add_cameras(site, count=12)
    results = await asyncio.gather(*(admit(site, camera) for camera in cameras))
    assert sum(len(result) for result in results) == 1
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(Camera).where(Camera.worker_id == site.places[0].worker.id)) == 1


async def test_concurrent_duplicate_admission_is_idempotent(site):
    camera = (await add_cameras(site))[0]
    results = await asyncio.gather(*(admit(site, camera) for _ in range(5)))
    assert sum(len(result) for result in results) == 1


@pytest.mark.parametrize("parent", [Factory, Zone])
async def test_disabled_camera_parent_is_not_admitted_or_exposed(site, parent):
    own = site.places[0]
    camera = (await add_cameras(site))[0]
    parent_id = own.factory.id if parent is Factory else own.zone.id
    async with AsyncSessionFactory() as db:
        await db.execute(update(parent).where(parent.id == parent_id).values(status="Inactive"))
        await db.commit()
    assert await admit(site, camera) == {}
    async with AsyncSessionFactory() as db:
        # Existing invalid rows must also fail closed at the stream boundary.
        await db.execute(update(Camera).where(Camera.id == camera.id).values(worker_id=own.worker.id))
        await db.commit()
        assert await WorkerSchedulingRepository(db).assignment_rows(own.worker.id) == []


async def test_backfill_does_not_steal_a_failed_workers_existing_camera(site):
    own = site.places[0]
    camera = (await add_cameras(site, worker=own.worker.id))[0]
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == own.worker.id).values(status="Offline"))
        spare = AIWorker(enterprise_id=site.enterprise.id, factory_id=own.factory.id,
                         max_cameras=1, worker_id=uuid4().hex, status="Online", last_heartbeat=datetime.now(timezone.utc))
        db.add(spare)
        await db.commit()
        assert await WorkerSchedulingRepository(db).admit_pending(
            site.enterprise.public_id, worker_public_id=spare.public_id) == {}
        assert await db.scalar(select(Camera.worker_id).where(Camera.id == camera.id)) == own.worker.id


@pytest.mark.parametrize("values", [
    {"factory_id": None}, {"max_cameras": 0}, {"status": "Offline"}, {"is_active": False},
    {"last_heartbeat": datetime.now(timezone.utc) - timedelta(minutes=5)},
    {"deleted_at": datetime.now(timezone.utc)},
])
async def test_unconfigured_stale_disabled_workers_receive_no_assignments(site, values):
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == site.places[0].worker.id).values(**values))
        await db.commit()
    assert await admit(site, (await add_cameras(site))[0]) == {}


async def test_poll_backfills_pending_cameras_after_worker_recovers(site):
    own = site.places[0]
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == own.worker.id).values(status="Offline"))
        await db.commit()
    cameras = await add_cameras(site, count=2)
    assert await admit(site, cameras[0]) == {}
    async with AsyncSessionFactory() as db:
        repo = WorkerRepository(db)
        worker = await repo.upsert_heartbeat(site.enterprise.public_id, own.worker.worker_id, "host", "model", True)
        assert worker.factory_id == own.factory.public_id and worker.max_cameras == 1
        response = await WorkerService(repo).get_worker_cameras_by_business_id(
            own.worker.worker_id, db, site.enterprise.public_id)
        assert len(response) == 1 and response[0]["camera_id"] == cameras[0].public_id
        assert response[0]["zone_config"]["ppe_required"] == ["helmet", "vest"]
        assert await db.scalar(select(Camera.worker_id).where(Camera.id == cameras[1].id)) is None


async def test_read_filters_legacy_foreign_factory_and_tenant_assignments(site):
    own = site.places[0]
    correct = (await add_cameras(site, worker=own.worker.id))[0]
    await add_cameras(site, place=1, worker=own.worker.id)
    await add_cameras(site, place=2, worker=own.worker.id)
    async with AsyncSessionFactory() as db:
        rows = await WorkerService(WorkerRepository(db)).get_worker_cameras(own.worker.id, db)
        assert [row["camera_id"] for row in rows] == [correct.public_id]
        assert rows[0]["factory_id"] == own.factory.public_id
        assert rows[0]["enterprise_id"] == site.enterprise.public_id
        await db.execute(update(AIWorker).where(AIWorker.id == own.worker.id).values(factory_id=None, max_cameras=0))
        await db.commit()
        assert await WorkerService(WorkerRepository(db)).get_worker_cameras(own.worker.id, db) == []


async def test_new_camera_service_returns_the_persisted_assignment(site):
    async with AsyncSessionFactory() as db:
        service = CameraService(CameraRepository(db), WorkerRepository(db))
        cam = await service.create_camera(site.enterprise.public_id, site.places[0].zone.public_id,
                                         "New camera", uuid4().hex, "rtsp://camera.example.invalid/feed", db)
        assert cam.worker_id == site.places[0].worker.public_id
        overflow = await service.create_camera(site.enterprise.public_id, site.places[0].zone.public_id,
                                              "Pending camera", uuid4().hex, "rtsp://camera.example.invalid/second-feed", db)
        assert overflow.worker_id is None


async def test_policy_conflicts_do_not_move_existing_assignments(site):
    own = site.places[0]
    await add_cameras(site, count=2, worker=own.worker.id)
    async with AsyncSessionFactory() as db:
        repo = WorkerSchedulingRepository(db)
        with pytest.raises(VisionGuardException) as exc:
            await repo.configure(own.worker.public_id, site.enterprise.public_id, own.factory.public_id, 1, "test-admin")
        assert exc.value.status_code == 409
        await db.rollback()
        with pytest.raises(VisionGuardException) as exc:
            await repo.configure(own.worker.public_id, site.enterprise.public_id, site.places[1].factory.public_id, 5, "test-admin")
        assert exc.value.status_code == 409
        await db.rollback()
        with pytest.raises(NotFoundException):
            await repo.configure(own.worker.public_id, site.enterprise.public_id, site.places[2].factory.public_id, 5, "test-admin")


async def test_capacity_change_and_admission_share_the_database_lock(site):
    own = site.places[0]
    camera = (await add_cameras(site))[0]
    # Hold the same policy lock while moving an empty worker to another factory.
    async with AsyncSessionFactory() as policy_db:
        repo = WorkerSchedulingRepository(policy_db)
        await repo._lock_enterprise(site.enterprise.public_id)
        task = asyncio.create_task(admit(site, camera))
        await asyncio.sleep(0.05)
        assert not task.done()
        await repo.configure(own.worker.public_id, site.enterprise.public_id, site.places[1].factory.public_id, 1, "test-admin")
    assert await task == {}


async def test_assignment_payload_query_count_is_constant_for_200_cameras(site):
    own = site.places[0]
    await add_cameras(site, count=200, worker=own.worker.id)
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == own.worker.id).values(max_cameras=200))
        await db.commit()
        statements = []
        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)
        event.listen(engine.sync_engine, "before_cursor_execute", capture)
        try:
            response = await WorkerService(WorkerRepository(db)).get_worker_cameras(own.worker.id, db)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert len(response) == 200
    assert len(statements) == 1  # Data retrieval only; no claim of camera inference capacity.


async def test_scheduling_endpoint_enforces_admin_tenant_and_valid_capacity(setup):
    s = setup
    path = f"/api/v1/workers/{s.worker.public_id}/scheduling"
    body = {"factory_id": s.places[0].factory.public_id, "max_cameras": 2}
    for user in ("viewer", "manager"):
        assert (await s.client.put(path, headers=headers(s, user), json=body)).status_code == 403
    assert (await s.client.put(path, headers=headers(s, "foreign"), json=body)).status_code == 404
    foreign = {**body, "factory_id": s.places[2].factory.public_id}
    assert (await s.client.put(path, headers=headers(s), json=foreign)).status_code == 404
    for limit in (0, -1, 10001, True, 1.5):
        response = await s.client.put(path, headers=headers(s), json={**body, "max_cameras": limit})
        assert response.status_code == 422
    response = await s.client.put(path, headers=headers(s), json=body)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["factory_id"] == body["factory_id"] and data["max_cameras"] == 2
    assert data["id"] == s.worker.public_id
    async with AsyncSessionFactory() as db:
        worker = await db.get(AIWorker, s.worker.id)
        assert worker.updated_by == s.users["admin"].public_id


async def test_heartbeat_cannot_self_authorize_factory_or_capacity(setup):
    from src.core.settings import settings
    s = setup
    h = {"X-Worker-Key": settings.WORKER_API_KEY, "X-Enterprise-Id": s.enterprise.public_id}
    for extra in ({"factory_id": s.places[1].factory.public_id}, {"max_cameras": 999}):
        response = await s.client.post("/api/v1/workers/heartbeat", headers=h,
                                      json={"worker_id": s.worker.worker_id, **extra})
        assert response.status_code == 422
    response = await s.client.post("/api/v1/workers/heartbeat", headers=h, json={"worker_id": s.worker.worker_id})
    assert response.status_code == 200
    assert response.json()["data"]["factory_id"] == s.places[0].factory.public_id
    assert response.json()["data"]["max_cameras"] == 1


@pytest.mark.parametrize("cuda_active", [False, True])
async def test_runtime_heartbeat_identity_roundtrips_without_changing_scheduling(setup, cuda_active):
    from src.core.settings import settings
    s = setup
    model_version = "ppe:" + "a" * 40  # Worker sends mode plus a checkpoint digest prefix.
    h = {"X-Worker-Key": settings.WORKER_API_KEY, "X-Enterprise-Id": s.enterprise.public_id}
    response = await s.client.post("/api/v1/workers/heartbeat", headers=h,
        json={"worker_id": s.worker.worker_id, "model_version": model_version, "gpu_available": cuda_active})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["model_version"] == model_version and data["gpu_available"] is cuda_active
    assert data["factory_id"] == s.places[0].factory.public_id and data["max_cameras"] == 1
    async with AsyncSessionFactory() as db:
        worker = await db.get(AIWorker, s.worker.id)
        assert worker.model_version == model_version and worker.gpu_available is cuda_active


async def test_complete_lease_renewal_select_count_is_constant_for_200_cameras(site):
    own = site.places[0]
    session_id = str(uuid4())
    await add_cameras(site, worker=own.worker.id)
    async def renew_and_count():
        async with AsyncSessionFactory() as db:
            # Warm first acquisition; count a steady-state full renewal poll.
            svc = WorkerService(WorkerRepository(db))
            await svc.get_worker_cameras_by_business_id(own.worker.worker_id, db, site.enterprise.public_id, session_id)
            statements = []
            def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
                if statement.lstrip().upper().startswith("SELECT"):
                    statements.append(statement)
            event.listen(engine.sync_engine, "before_cursor_execute", capture)
            try:
                response = await svc.get_worker_cameras_by_business_id(own.worker.worker_id, db, site.enterprise.public_id, session_id)
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", capture)
        return len(response), len(statements)
    small_size, small_queries = await renew_and_count()
    await add_cameras(site, count=199, worker=own.worker.id)
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == own.worker.id).values(max_cameras=200))
        await db.commit()
    large_size, large_queries = await renew_and_count()
    assert small_size == 1 and large_size == 200
    assert small_queries == large_queries and large_queries <= 25
