"""Real PostgreSQL ownership races, replay and process-session fencing."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from src.core.exceptions import VisionGuardException
from src.modules.worker.infrastructure.leases import CameraLeaseRepository, fence_camera_event
from src.shared.database.models import AIWorker, Camera, CameraLease, Factory, Zone, PPEViolation, Alert
from src.shared.database.session import AsyncSessionFactory
from tests.test_worker_scheduling import site as site, add_cameras, pytestmark as pytestmark
from tests.test_review_integration import setup as setup, event


async def acquire(site, worker=None, session=None):
    async with AsyncSessionFactory() as db:
        return await CameraLeaseRepository(db).acquire(site.enterprise.public_id,
            (worker or site.places[0].worker).id, session or str(uuid4()))


async def standby(site, capacity=1):
    async with AsyncSessionFactory() as db:
        worker = AIWorker(enterprise_id=site.enterprise.id, factory_id=site.places[0].factory.id,
            worker_id=uuid4().hex, max_cameras=capacity, status="Online", last_heartbeat=datetime.now(timezone.utc))
        db.add(worker)
        await db.commit()
        return worker


async def expire(token):
    async with AsyncSessionFactory() as db:
        await db.execute(update(CameraLease).where(CameraLease.token == token).values(
            expires_at=func.clock_timestamp() - timedelta(seconds=1)))
        await db.commit()


def body_for(camera, worker, grant):
    return {"camera_id": camera.public_id, "worker_id": worker.worker_id,
        "camera_lease": {**grant, "observed_at": grant["server_time"]}}


async def test_live_owner_not_stolen_even_with_stale_heartbeat_and_duplicate_process(site):
    camera = (await add_cameras(site, worker=site.places[0].worker.id))[0]
    session = str(uuid4())
    first = (await acquire(site, session=session))[camera.public_id]
    renewed = (await acquire(site, session=session))[camera.public_id]
    assert renewed["token"] == first["token"] and renewed["generation"] == 1
    with pytest.raises(VisionGuardException, match="Another process"):
        await acquire(site)
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == site.places[0].worker.id).values(
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=5)))
        await db.commit()
    assert await acquire(site, await standby(site)) == {}
    assert await acquire(site, session=session) == {}


async def test_expiry_race_has_one_winner_and_recovered_old_owner_cannot_reclaim(site):
    owner = site.places[0].worker
    camera = (await add_cameras(site, worker=owner.id))[0]
    original = (await acquire(site))[camera.public_id]
    a, b = await standby(site), await standby(site)
    await expire(original["token"])
    results = await asyncio.gather(acquire(site, a), acquire(site, b))
    winners = [r[camera.public_id] for r in results if camera.public_id in r]
    assert len(winners) == 1 and winners[0]["generation"] == 2
    assert winners[0]["token"] != original["token"]
    assert await acquire(site, owner) == {}
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(CameraLease).where(CameraLease.camera_id == camera.id)) == 2


async def test_standby_capacity_and_factory_limits_and_legacy_nontransfer(site):
    owner = site.places[0].worker
    cameras = await add_cameras(site, count=3, worker=owner.id)
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == owner.id).values(max_cameras=3))
        await db.commit()
    grants = await acquire(site)
    for grant in grants.values():
        await expire(grant["token"])
    assert await acquire(site, site.places[1].worker) == {}
    spare = await standby(site)
    assert len(await acquire(site, spare)) == 1
    legacy = (await add_cameras(site, worker=owner.id))[0]
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(Camera.worker_id).where(Camera.id == legacy.id)) == owner.id
        assert await db.scalar(select(func.count()).select_from(Camera).where(
            Camera.id.in_([c.id for c in cameras]), Camera.worker_id == spare.id)) == 1


@pytest.mark.parametrize("kind", ["missing", "token", "session", "generation", "worker", "late", "future"])
async def test_invalid_event_fences(site, kind):
    owner = site.places[0].worker
    camera = (await add_cameras(site, worker=owner.id))[0]
    grant = (await acquire(site))[camera.public_id]
    body = body_for(camera, owner, grant)
    if kind == "missing":
        body.pop("camera_lease")
    elif kind == "worker":
        body["worker_id"] = "foreign-worker"
    elif kind in {"token", "session", "generation"}:
        key = "session_id" if kind == "session" else kind
        body["camera_lease"][key] = 99 if kind == "generation" else str(uuid4())
    elif kind == "late":
        body["camera_lease"]["observed_at"] = grant["expires_at"]
    else:
        body["camera_lease"]["observed_at"] = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    async with AsyncSessionFactory() as db:
        with pytest.raises(ValueError):
            await fence_camera_event(db, body, historical=True)


async def test_valid_history_replays_but_old_telemetry_is_rejected_after_takeover(site):
    owner = site.places[0].worker
    camera = (await add_cameras(site, worker=owner.id))[0]
    grant = (await acquire(site))[camera.public_id]
    # Advance the entire original lease into the past without waiting 90 seconds.
    async with AsyncSessionFactory() as db:
        start = datetime.now(timezone.utc) - timedelta(seconds=100)
        await db.execute(update(CameraLease).where(CameraLease.token == grant["token"]).values(
            started_at=start, expires_at=start + timedelta(seconds=90)))
        await db.commit()
    grant["server_time"] = (start + timedelta(seconds=10)).isoformat()
    await acquire(site, await standby(site))
    body = body_for(camera, owner, grant)
    async with AsyncSessionFactory() as db:
        await fence_camera_event(db, body, historical=True)
        with pytest.raises(ValueError, match="Stale camera telemetry"):
            await fence_camera_event(db, body)


async def test_event_transaction_holds_fence_until_commit(site):
    camera = (await add_cameras(site, worker=site.places[0].worker.id))[0]
    grant = (await acquire(site))[camera.public_id]
    spare = await standby(site)
    # A historical event holds an expired camera row while a takeover waits.
    # A different LIVE owner's row is no longer a takeover candidate.
    start = datetime.now(timezone.utc) - timedelta(seconds=100)
    async with AsyncSessionFactory() as db:
        await db.execute(update(CameraLease).where(CameraLease.token == grant["token"]).values(
            started_at=start, expires_at=start + timedelta(seconds=90)))
        await db.commit()
    grant["server_time"] = (start + timedelta(seconds=10)).isoformat()
    async with AsyncSessionFactory() as db:
        await fence_camera_event(db, body_for(camera, site.places[0].worker, grant), historical=True)
        task = asyncio.create_task(acquire(site, spare))
        await asyncio.sleep(.1)
        assert not task.done()
        await db.commit()
    result = await task
    assert result[camera.public_id]["generation"] == 2


@pytest.mark.parametrize("parent", [Factory, Zone])
async def test_inactive_parent_prevents_renewal_and_failover(site, parent):
    own = site.places[0]
    camera = (await add_cameras(site, worker=own.worker.id))[0]
    grant = (await acquire(site))[camera.public_id]
    await expire(grant["token"])
    spare = await standby(site)
    async with AsyncSessionFactory() as db:
        pk = own.factory.id if parent is Factory else own.zone.id
        await db.execute(update(parent).where(parent.id == pk).values(status="Inactive"))
        await db.commit()
    assert await acquire(site, spare) == {} and await acquire(site) == {}


async def test_api_requires_session_and_rejects_concurrent_duplicate_process(setup):
    from src.core.settings import settings
    s = setup
    h = {"X-Worker-Key": settings.WORKER_API_KEY, "X-Enterprise-Id": s.enterprise.public_id}
    url = f"/api/v1/workers/{s.worker.worker_id}/cameras"
    assert (await s.client.get(url, headers=h)).status_code == 422
    h["X-Worker-Session"] = str(uuid4())
    result = await s.client.get(url, headers=h)
    assert result.status_code == 200 and len(result.json()["data"]) == 1
    grant = result.json()["data"][0]["lease"]
    assert grant["session_id"] == h["X-Worker-Session"] and grant["ttl_seconds"] == 90
    h["X-Worker-Session"] = str(uuid4())
    assert (await s.client.get(url, headers=h)).status_code == 409


async def test_consumer_replays_valid_prior_owner_once_and_rejects_expired_observation(setup):
    from src.shared.messaging.consumer import _route_event
    s = setup
    camera = s.places[0].camera
    async with AsyncSessionFactory() as db:
        grants = await CameraLeaseRepository(db).acquire(s.enterprise.public_id, s.worker.id, str(uuid4()))
        grant = grants[camera.public_id]
        start = datetime.now(timezone.utc) - timedelta(seconds=100)
        await db.execute(update(CameraLease).where(CameraLease.token == grant["token"]).values(
            started_at=start, expires_at=start + timedelta(seconds=90)))
        await db.commit()
        # Restart the same worker ID with a fresh process session.
        assert (await CameraLeaseRepository(db).acquire(s.enterprise.public_id, s.worker.id, str(uuid4())))[camera.public_id]["generation"] == 2
    body = {**event(s), "worker_id": s.worker.worker_id, "camera_lease": {
        **grant, "observed_at": (start + timedelta(seconds=10)).isoformat()}}
    with patch("src.modules.realtime.manager.manager.broadcast", new=AsyncMock()):
        await _route_event("events.helmet_missing_detected", body)
        await _route_event("events.helmet_missing_detected", body)
        with pytest.raises(ValueError):
            await _route_event("events.helmet_missing_detected", {**body, "event_id": str(uuid4()),
                "camera_lease": {**body["camera_lease"], "observed_at": datetime.now(timezone.utc).isoformat()}})
        for route in ("events.camera_reconnected", "events.camera_offline_detected", "events.occupancy_updated"):
            with pytest.raises(ValueError):
                await _route_event(route, body)
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(PPEViolation).where(PPEViolation.camera_id == camera.id)) == 1
        assert await db.scalar(select(func.count()).select_from(Alert).where(Alert.camera_id == camera.id)) == 1


async def test_legacy_owner_and_foreign_tenant_are_never_taken_over(site):
    owner = site.places[0].worker
    camera = (await add_cameras(site, worker=owner.id))[0]
    spare = await standby(site)
    async with AsyncSessionFactory() as db:
        await db.execute(update(AIWorker).where(AIWorker.id == owner.id).values(status="Offline"))
        await db.commit()
    assert await acquire(site, spare) == {}
    assert await acquire(site, site.places[2].worker) == {}
    async with AsyncSessionFactory() as db:
        row = await db.get(Camera, camera.id)
        assert row.worker_id == owner.id and row.assignment_generation == 0


async def test_missing_current_lease_history_fails_closed(site):
    from sqlalchemy import delete
    camera = (await add_cameras(site, worker=site.places[0].worker.id))[0]
    grant = (await acquire(site))[camera.public_id]
    async with AsyncSessionFactory() as db:
        await db.execute(delete(CameraLease).where(CameraLease.token == grant["token"]))
        await db.commit()
    with pytest.raises(VisionGuardException, match="history is missing"):
        await acquire(site, await standby(site))


async def test_renewal_does_not_lock_another_workers_live_cameras(site):
    camera = (await add_cameras(site, worker=site.places[0].worker.id))[0]
    grant = (await acquire(site))[camera.public_id]
    spare = await standby(site)
    other = (await add_cameras(site, worker=spare.id))[0]
    session = str(uuid4())
    await acquire(site, spare, session)
    async with AsyncSessionFactory() as db:
        await fence_camera_event(db, body_for(camera, site.places[0].worker, grant))
        result = await asyncio.wait_for(acquire(site, spare, session), 2)
        assert list(result) == [other.public_id]
