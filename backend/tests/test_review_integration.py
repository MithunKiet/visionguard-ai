"""Regression checks against migrated PostgreSQL and Redis; no external delivery."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, update

from src.core.app import create_app
from src.modules.identity.application.services import AuthService
from src.modules.identity.infrastructure.repositories import UserRepository
from src.shared.cache.client import init_redis, close_redis
from src.shared.database.models import (
    AIWorker, Alert, Camera, Department, Enterprise, Factory, PPEViolation,
    Role, User, UserRole, Zone, ZoneConfig,
)
from src.shared.database.session import AsyncSessionFactory, engine
from src.shared.security.password import hash_password

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable TEST_DATABASE_URL and Redis")


@pytest.fixture
async def setup():
    await init_redis()
    async with AsyncSessionFactory() as db:
        enterprise = Enterprise(name="Test A", code=uuid4().hex)
        other = Enterprise(name="Test B", code=uuid4().hex)
        db.add_all([enterprise, other])
        await db.flush()
        locations = []
        for ent in [enterprise, enterprise, other]:
            factory = Factory(enterprise_id=ent.id, name="Factory", code=uuid4().hex)
            db.add(factory)
            await db.flush()
            department = Department(enterprise_id=ent.id, factory_id=factory.id, name="Department", code=uuid4().hex)
            db.add(department)
            await db.flush()
            zone = Zone(enterprise_id=ent.id, factory_id=factory.id, department_id=department.id, name="Zone", code=uuid4().hex, max_occupancy=10)
            db.add(zone)
            await db.flush()
            camera = Camera(enterprise_id=ent.id, factory_id=factory.id, zone_id=zone.id,
                            name="Camera", code=uuid4().hex, rtsp_url="rtsp://camera.example.invalid/feed")
            config = ZoneConfig(enterprise_id=ent.id, zone_id=zone.id)
            db.add_all([camera, config])
            await db.flush()
            locations.append(SimpleNamespace(factory=factory, department=department, zone=zone, camera=camera, config=config))
        users = {}
        for name, code, ent in [("admin", "ENTERPRISE_ADMIN", enterprise), ("manager", "FACTORY_MANAGER", enterprise),
                                 ("viewer", "VIEWER", enterprise), ("foreign", "ENTERPRISE_ADMIN", other)]:
            role = await db.scalar(select(Role).where(Role.code == code))
            user = User(enterprise_id=ent.id, name=name, email=f"{uuid4().hex}@example.com",
                        password_hash=hash_password("Test-password-391"), is_first_login=False,
                        status="Active", factory_id=locations[0].factory.id if ent is enterprise else locations[2].factory.id,
                        assigned_zone_ids=[locations[0].zone.public_id] if name == "viewer" else [])
            db.add(user)
            await db.flush()
            db.add(UserRole(user_public_id=user.public_id, role_public_id=role.public_id))
            users[name] = user
        worker = AIWorker(enterprise_id=enterprise.id, worker_id=uuid4().hex, status="Online")
        db.add(worker)
        await db.commit()
        tokens = {}
        for name, user in users.items():
            entity = await UserRepository(db).get_by_id(user.public_id)
            tokens[name] = AuthService(db)._make_access_token(entity)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="https://test") as client:
        yield SimpleNamespace(client=client, enterprise=enterprise, other=other, places=locations,
                              users=users, tokens=tokens, worker=worker)
    await close_redis()
    await engine.dispose()


def headers(setup, name="admin"):
    return {"Authorization": f"Bearer {setup.tokens[name]}"}


async def test_factory_scope_covers_details_config_maintenance_and_camera_create(setup):
    s = setup
    own, forbidden, _ = s.places
    h = headers(s, "manager")
    for path in [f"/factories/{forbidden.factory.public_id}", f"/departments/{forbidden.department.public_id}",
                 f"/config/zone/{forbidden.zone.public_id}"]:
        assert (await s.client.get("/api/v1" + path, headers=h)).status_code == 404
    assert (await s.client.get(f"/api/v1/factories/{own.factory.public_id}", headers=h)).status_code == 200
    assert (await s.client.post(f"/api/v1/maintenance/camera/{forbidden.camera.public_id}/enable", headers=h, json={})).status_code == 404
    assert (await s.client.post("/api/v1/cameras", headers=h, json={"zone_id": forbidden.zone.public_id,
        "name": "Blocked", "code": "BLOCKED", "rtsp_url": "rtsp://camera.example.invalid/feed"})).status_code == 404


async def test_cross_tenant_and_parent_references_rejected(setup):
    s = setup
    a, b, foreign = s.places
    cases = [("/departments", {"factory_id": foreign.factory.public_id, "name": "Bad", "code": "BAD"}),
             ("/notifications/recipients", {"user_id": s.users["foreign"].public_id, "zone_id": a.zone.public_id}),
             ("/zones", {"factory_id": a.factory.public_id, "department_id": b.department.public_id, "name": "Bad", "code": "BAD"})]
    for path, body in cases:
        response = await s.client.post("/api/v1" + path, headers=headers(s), json=body)
        assert response.status_code in {403, 404}, response.text


async def test_logout_and_deactivation_revoke_access(setup):
    s = setup
    assert (await s.client.post("/api/v1/auth/logout", headers=headers(s))).status_code == 200
    assert (await s.client.get("/api/v1/auth/me", headers=headers(s))).status_code == 401
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users["manager"].id).values(status="Inactive"))
        await db.commit()
    assert (await s.client.get("/api/v1/auth/me", headers=headers(s, "manager"))).status_code == 401


@pytest.mark.parametrize("credential_state", ["expired", "missing", "tampered", "suspended"])
async def test_logout_revokes_refresh_without_a_current_access_session(setup, credential_state):
    import jwt
    from src.core.settings import settings
    from src.shared.security.jwt import decode_token

    s = setup
    login = await s.client.post("/api/v1/auth/login", json={
        "email": s.users["admin"].email, "password": "Test-password-391",
    })
    assert login.status_code == 200
    session = login.json()["data"]
    assert "refresh_token" in s.client.cookies
    if credential_state == "suspended":
        async with AsyncSessionFactory() as db:
            await db.execute(update(User).where(User.id == s.users["admin"].id).values(status="Inactive"))
            await db.commit()
    claims = decode_token(session["access_token"])
    if credential_state == "expired":
        claims["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    signing_key = "invalid-signature-test-key-at-least-thirty-two-characters" if credential_state == "tampered" else settings.JWT_SECRET
    access = jwt.encode(claims, signing_key, algorithm=settings.JWT_ALGORITHM)
    auth = {} if credential_state == "missing" else {"Authorization": f"Bearer {access}"}
    assert (await s.client.get("/api/v1/auth/me", headers=auth)).status_code == 401
    response = await s.client.post("/api/v1/auth/logout", headers=auth)
    assert response.status_code == 200
    assert "refresh_token" not in s.client.cookies
    # Reactivation cannot make the logged-out refresh token usable again.
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users["admin"].id).values(status="Active"))
        await db.commit()
    assert (await s.client.post("/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]})).status_code == 401
    assert (await s.client.post("/api/v1/auth/logout", headers=auth)).status_code == 200
    if credential_state in {"missing", "tampered"}:
        # An unverified JWT must not blacklist a different valid credential.
        assert (await s.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {session['access_token']}"})).status_code == 200


async def test_manual_camera_reactivation_survives_stream_updates_and_worker_poll(setup):
    from src.core.settings import settings
    from src.shared.messaging.consumer import _route_event

    s = setup
    camera = s.places[0].camera
    async with AsyncSessionFactory() as db:
        await db.execute(update(Camera).where(Camera.id == camera.id).values(worker_id=s.worker.id))
        await db.commit()
    path = f"/api/v1/cameras/{camera.public_id}/status"
    worker_headers = {"X-Worker-Key": settings.WORKER_API_KEY, "X-Enterprise-Id": s.enterprise.public_id}
    async def persisted_status():
        async with AsyncSessionFactory() as db:
            return await db.scalar(select(Camera.status).where(Camera.id == camera.id))

    with patch("src.shared.messaging.publisher.publish_config_event", new=AsyncMock()), patch(
        "src.modules.realtime.manager.manager.broadcast", new=AsyncMock()) as broadcast:
        off = await s.client.patch(path, headers=headers(s), json={"status": "Inactive"})
        assert off.status_code == 200
        for route in ["events.camera_reconnected", "events.camera_offline_detected"]:
            await _route_event(route, event(s))
            assert await persisted_status() == "Inactive"
        broadcast.assert_not_awaited()
        on = await s.client.patch(path, headers=headers(s), json={"status": "Active"})
        assert on.status_code == 200 and on.json()["data"]["status"] == "Active"
        assert await persisted_status() == "Active"
        poll = await s.client.get(f"/api/v1/workers/{s.worker.worker_id}/cameras", headers=worker_headers)
        assert poll.status_code == 200 and poll.json()["data"][0]["status"] == "Active"
        await _route_event("events.camera_offline_detected", event(s))
        assert await persisted_status() == "Offline"
        await _route_event("events.camera_reconnected", event(s))
        assert await persisted_status() == "Active"
        assert broadcast.await_count == 2


async def test_current_permissions_override_stale_token(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users["manager"].id).values(factory_id=s.places[1].factory.id))
        await db.commit()
    response = await s.client.get(f"/api/v1/factories/{s.places[0].factory.public_id}", headers=headers(s, "manager"))
    assert response.status_code == 404


async def test_refresh_rotation_is_single_use_under_concurrency(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        result = await AuthService(db).login(s.users["admin"].email, "Test-password-391")
    async def refresh():
        async with AsyncSessionFactory() as db:
            try:
                await AuthService(db).refresh(result["refresh_token"])
                return True
            except Exception as exc:
                from src.core.exceptions import UnauthorizedException
                assert isinstance(exc, UnauthorizedException)
                return False
    assert sum(await asyncio.gather(*(refresh() for _ in range(4)))) == 1


async def test_password_change_invalidates_access_and_refresh(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        svc = AuthService(db)
        result = await svc.login(s.users["admin"].email, "Test-password-391")
        await svc.change_password(s.users["admin"].public_id, "Test-password-391", "Replacement-password-582")
    assert (await s.client.get("/api/v1/auth/me", headers=headers(s))).status_code == 401
    assert (await s.client.post("/api/v1/auth/refresh", json={"refresh_token": result["refresh_token"]})).status_code == 401


async def test_first_login_requires_password_change(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users["admin"].id).values(is_first_login=True))
        await db.commit()
    assert (await s.client.get("/api/v1/auth/me", headers=headers(s))).status_code == 200
    assert (await s.client.get("/api/v1/factories", headers=headers(s))).status_code == 403


async def test_worker_wrong_tenant_cannot_read_or_update(setup):
    s = setup
    from src.core.settings import settings
    h = {"X-Worker-Key": settings.WORKER_API_KEY, "X-Enterprise-Id": s.other.public_id}
    assert (await s.client.get(f"/api/v1/workers/{s.worker.worker_id}/cameras", headers=h)).status_code == 404
    response = await s.client.post("/api/v1/workers/heartbeat", headers=h, json={"worker_id": s.worker.worker_id, "gpu_available": False})
    assert response.status_code == 403


async def test_rtsp_probe_rejects_files_and_viewers(setup):
    s = setup
    assert (await s.client.post("/api/v1/cameras/test-connection", headers=headers(s), json={"rtsp_url": "/tmp/frame.jpg"})).status_code == 422
    assert (await s.client.post("/api/v1/cameras/test-connection", headers=headers(s, "viewer"), json={"rtsp_url": "rtsp://camera.example.invalid/feed"})).status_code == 403


def event(s, place=0):
    p = s.places[place]
    return {"event_id": str(uuid4()), "enterprise_id": s.enterprise.public_id if place < 2 else s.other.public_id,
            "factory_id": p.factory.public_id, "zone_id": p.zone.public_id, "camera_id": p.camera.public_id,
            "confidence": 0.95, "timestamp": "2020-01-02T03:04:05+00:00", "track_id": 7, "bbox": [1, 2, 3, 4]}


async def test_event_replay_is_atomic_and_preserves_detection_time(setup):
    s = setup
    from src.shared.messaging.consumer import _route_event
    payload = event(s)
    with patch("src.modules.realtime.manager.manager.broadcast", new=AsyncMock()), patch(
        "src.modules.notifications.application.services.NotificationService.notify_zone_violation", new=AsyncMock(return_value=[])):
        await asyncio.gather(*(_route_event("events.helmet_missing_detected", dict(payload)) for _ in range(3)))
    async with AsyncSessionFactory() as db:
        rows = (await db.execute(select(PPEViolation).where(PPEViolation.camera_id == s.places[0].camera.id))).scalars().all()
        assert len(rows) == 1
        assert rows[0].created_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert rows[0].track_id == "7" and rows[0].bbox == [1, 2, 3, 4]
        assert await db.scalar(select(func.count()).select_from(Alert).where(Alert.camera_id == s.places[0].camera.id)) == 1


async def test_low_confidence_is_persisted_without_alert(setup):
    s = setup
    from src.shared.messaging.consumer import _route_event
    payload = {**event(s), "confidence": 0.65, "review": True, "violation_type": "no_helmet"}
    with patch("src.modules.realtime.manager.manager.broadcast", new=AsyncMock()):
        await _route_event("events.low_confidence_violation", payload)
    async with AsyncSessionFactory() as db:
        row = await db.scalar(select(PPEViolation).where(PPEViolation.camera_id == s.places[0].camera.id))
        assert row.needs_review
        assert await db.scalar(select(func.count()).select_from(Alert).where(Alert.camera_id == s.places[0].camera.id)) == 0


async def test_config_updates_have_distinct_versions(setup):
    s = setup
    from src.modules.config.application.services import ConfigService
    async def save(threshold):
        async with AsyncSessionFactory() as db:
            result = await ConfigService(db).update_zone_config(s.places[0].zone.public_id, s.enterprise.public_id,
                {"helmet_threshold": threshold}, s.users["admin"].public_id)
            return result["version"]
    with patch("src.modules.config.application.services.publish_config_event", new=AsyncMock()):
        assert sorted(await asyncio.gather(save(0.8), save(0.9))) == [2, 3]


async def test_alert_numbers_unique_across_tenants_and_false_positive_propagates(setup):
    s = setup
    from src.shared.messaging.consumer import _route_event
    with patch("src.modules.realtime.manager.manager.broadcast", new=AsyncMock()), patch(
        "src.modules.notifications.application.services.NotificationService.notify_zone_violation", new=AsyncMock(return_value=[])):
        await asyncio.gather(_route_event("events.helmet_missing_detected", event(s)),
                             _route_event("events.helmet_missing_detected", event(s, 2)))
    async with AsyncSessionFactory() as db:
        alerts = (await db.execute(select(Alert).where(Alert.camera_id.in_([s.places[0].camera.id, s.places[2].camera.id])))).scalars().all()
        assert len({a.alert_number for a in alerts}) == 2
        own = next(a for a in alerts if a.enterprise_id == s.enterprise.id)
    response = await s.client.patch(f"/api/v1/alerts/{own.public_id}/false-positive", headers=headers(s), json={"reason": "Validated false positive"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["resolved_on"]
    async with AsyncSessionFactory() as db:
        assert (await db.get(PPEViolation, own.violation_id)).is_false_positive


async def test_failed_alert_write_rolls_back_receipt_and_violation(setup):
    s = setup
    from src.shared.messaging.consumer import _route_event
    from src.shared.database.models import EventReceipt
    payload = event(s)
    with patch("src.modules.alerts.infrastructure.repositories.AlertRepository.create", new=AsyncMock(side_effect=RuntimeError("Injected storage failure"))):
        with pytest.raises(RuntimeError, match="Injected storage failure"):
            await _route_event("events.helmet_missing_detected", payload)
    async with AsyncSessionFactory() as db:
        assert await db.get(EventReceipt, payload["event_id"]) is None
        assert await db.scalar(select(func.count()).select_from(PPEViolation).where(PPEViolation.camera_id == s.places[0].camera.id)) == 0


async def test_redis_fanout_reaches_both_replicas_and_enforces_scope(setup):
    from src.modules.realtime.manager import ConnectionManager
    s = setup
    class Socket:
        def __init__(self):
            self.messages = []
            self.arrived = asyncio.Event()
            self.closed = False
        async def accept(self, **kwargs):
            pass
        async def send_text(self, message):
            self.messages.append(message)
            self.arrived.set()
        async def close(self, **kwargs):
            self.closed = True
    first, second = ConnectionManager(), ConnectionManager()
    admin, manager = Socket(), Socket()
    await first.start()
    await second.start()
    try:
        await first.connect(s.enterprise.public_id, admin, s.tokens["admin"])
        await second.connect(s.enterprise.public_id, manager, s.tokens["manager"])
        await first.broadcast(s.enterprise.public_id, {"type": "camera.status_changed", "data": {"camera_id": s.places[0].camera.public_id}})
        await asyncio.wait_for(asyncio.gather(admin.arrived.wait(), manager.arrived.wait()), 3)
        assert len(admin.messages) == len(manager.messages) == 1
        # Direct delivery test avoids depending on timing for a negative assertion.
        await second._deliver(s.enterprise.public_id, {"type": "camera.status_changed", "data": {"camera_id": s.places[1].camera.public_id}})
        assert len(manager.messages) == 1
        await s.client.post("/api/v1/auth/logout", headers=headers(s, "manager"))
        await second._deliver(s.enterprise.public_id, {"type": "camera.status_changed", "data": {"camera_id": s.places[0].camera.public_id}})
        assert manager.closed and len(manager.messages) == 1
    finally:
        await first.stop()
        await second.stop()


async def test_mfa_enabled_account_cannot_bypass_unimplemented_challenge(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        result = await AuthService(db).login(s.users["admin"].email, "Test-password-391")
        await db.execute(update(User).where(User.id == s.users["admin"].id).values(totp_enabled=True))
        await db.commit()
    assert (await s.client.get("/api/v1/auth/me", headers=headers(s))).status_code == 401
    assert (await s.client.post("/api/v1/auth/refresh", json={"refresh_token": result["refresh_token"]})).status_code == 401
    assert (await s.client.post("/api/v1/auth/login", json={"email": s.users["admin"].email, "password": "Test-password-391"})).status_code == 403


async def test_bound_worker_credential_rejects_different_worker_and_tenant(setup, monkeypatch):
    s = setup
    from src.core.settings import settings
    monkeypatch.setattr(settings, "WORKER_CREDENTIALS", {s.worker.worker_id: {"key": "test-worker-credential", "enterprise_id": s.enterprise.public_id}})
    h = {"X-Worker-Key": "test-worker-credential", "X-Enterprise-Id": s.enterprise.public_id}
    assert (await s.client.get(f"/api/v1/workers/{s.worker.worker_id}/cameras", headers=h)).status_code == 200
    assert (await s.client.get("/api/v1/workers/another-worker/cameras", headers=h)).status_code == 403
    h["X-Enterprise-Id"] = s.other.public_id
    assert (await s.client.get(f"/api/v1/workers/{s.worker.worker_id}/cameras", headers=h)).status_code == 401
