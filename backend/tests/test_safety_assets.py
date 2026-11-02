"""Fire extinguisher asset registry, policy delivery and incident handling.

Unit checks run anywhere; the API/consumer checks need the disposable
PostgreSQL + Redis used by the other integration suites. None of this
measures detection accuracy on real cameras."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import cv2
import numpy as np
import pytest
from sqlalchemy import func, select, update

from src.modules.assets.application.events import handle_asset_incident
from src.modules.assets.application.services import monitoring_status

ROOT = Path(__file__).resolve().parents[2]
needs_db = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable TEST_DATABASE_URL and Redis")


def test_backend_and_worker_fingerprints_are_identical():
    worker = ROOT / "ai-worker" / "src" / "pipeline" / "asset_fingerprint.py"
    if not worker.exists():
        pytest.skip("Worker sources are not part of this checkout")
    backend = ROOT / "backend" / "src" / "modules" / "assets" / "domain" / "fingerprint.py"
    assert backend.read_bytes() == worker.read_bytes()


def _asset(**values):
    base = dict(monitoring_enabled=True, roi_fingerprint="r", scene_fingerprint="s", check_interval_seconds=60,
                last_checked_at=datetime.now(timezone.utc), last_state="OK")
    return type("Asset", (), {**base, **values})()


def test_monitoring_status_is_unconfirmed_until_a_fresh_worker_report():
    now = datetime.now(timezone.utc)
    assert monitoring_status(_asset(monitoring_enabled=False), now) == "Disabled"
    assert monitoring_status(_asset(roi_fingerprint=None), now) == "NotConfigured"
    assert monitoring_status(_asset(last_checked_at=None), now) == "Unconfirmed"
    assert monitoring_status(_asset(last_checked_at=now - timedelta(seconds=181)), now) == "Unconfirmed"
    assert monitoring_status(_asset(last_state="Changed"), now) == "Changed"


async def test_incident_event_requires_ownership_fields():
    with pytest.raises(ValueError):
        await handle_asset_incident("events.asset_area_changed", {"event_id": str(uuid4()), "camera_id": "x"})


def _reference_jpeg():
    rng = np.random.default_rng(3)
    frame = rng.integers(60, 200, size=(360, 640, 3), dtype=np.uint8)
    frame[100:260, 400:460] = (30, 30, 200)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


# ── Integration ───────────────────────────────────────────────────────────

if os.environ.get("TEST_DATABASE_URL"):
    from tests.test_review_integration import setup as setup, headers  # noqa: F401


@pytest.fixture
def storage():
    objects = {}

    async def store(key, content):
        objects[key] = content

    async def read(key):
        return objects[key]

    with patch("src.modules.assets.application.services.store_image", new=store), \
         patch("src.modules.assets.application.services.read_image", new=read), \
         patch("src.modules.camera.application.probe.capture_still", new=AsyncMock(return_value=_reference_jpeg())):
        yield objects


async def _monitored_asset(s, storage, place=0, code=None):
    created = await s.client.post("/api/v1/safety-assets", headers=headers(s), json={
        "camera_id": s.places[place].camera.public_id, "asset_code": code or f"FE-{uuid4().hex[:8]}", "name": "CO2 extinguisher"})
    assert created.status_code == 200, created.text
    asset = created.json()["data"]
    captured = await s.client.post(f"/api/v1/safety-assets/{asset['id']}/reference", headers=headers(s))
    assert captured.status_code == 200, captured.text
    saved = await s.client.put(f"/api/v1/safety-assets/{asset['id']}", headers=headers(s), json={
        "version": captured.json()["data"]["version"], "roi": {"x": 0.62, "y": 0.27, "width": 0.1, "height": 0.45},
        "monitoring_enabled": True})
    assert saved.status_code == 200, saved.text
    return saved.json()["data"]


def _event(s, asset_id, place=0, **values):
    p = s.places[place]
    prefix = f"{s.enterprise.public_id}/{p.factory.public_id}/{p.zone.public_id}/{p.camera.public_id}"
    event_id = str(uuid4())
    return {"event_id": event_id, "enterprise_id": s.enterprise.public_id, "factory_id": p.factory.public_id,
            "zone_id": p.zone.public_id, "camera_id": p.camera.public_id, "asset_id": asset_id,
            "similarity": 0.12, "scene_similarity": 0.93, "snapshot_key": f"{prefix}/{event_id}.jpg",
            "config_version": 2, "timestamp": datetime.now(timezone.utc).isoformat(), **values}


@needs_db
async def test_monitoring_requires_reference_and_scope_is_enforced(setup, storage):
    s = setup
    created = await s.client.post("/api/v1/safety-assets", headers=headers(s), json={
        "camera_id": s.places[0].camera.public_id, "asset_code": f"FE-{uuid4().hex[:8]}", "name": "Extinguisher"})
    asset = created.json()["data"]
    assert asset["monitoring_status"] == "Disabled" and not asset["has_reference"]
    early = await s.client.put(f"/api/v1/safety-assets/{asset['id']}", headers=headers(s),
                               json={"version": asset["version"], "monitoring_enabled": True})
    assert early.status_code == 422
    stale = await s.client.put(f"/api/v1/safety-assets/{asset['id']}", headers=headers(s),
                               json={"version": asset["version"] + 5, "name": "Renamed"})
    assert stale.status_code == 409
    duplicate = await s.client.post("/api/v1/safety-assets", headers=headers(s), json={
        "camera_id": s.places[0].camera.public_id, "asset_code": asset["asset_code"], "name": "Copy"})
    assert duplicate.status_code == 409
    # Factory manager owns place 0 only; viewers cannot manage.
    foreign = await s.client.post("/api/v1/safety-assets", headers=headers(s, "manager"), json={
        "camera_id": s.places[1].camera.public_id, "asset_code": "FE-X", "name": "Blocked"})
    assert foreign.status_code == 404
    assert (await s.client.post("/api/v1/safety-assets", headers=headers(s, "viewer"), json={
        "camera_id": s.places[0].camera.public_id, "asset_code": "FE-Y", "name": "Blocked"})).status_code == 403
    assert (await s.client.get(f"/api/v1/safety-assets/{asset['id']}", headers=headers(s, "foreign"))).status_code == 404


@needs_db
async def test_monitored_asset_reaches_push_and_worker_poll_with_identical_entries(setup, storage):
    from src.shared.database.models import ConfigDelivery
    from src.shared.database.session import AsyncSessionFactory
    from src.modules.worker.application.services import WorkerService
    from src.modules.worker.infrastructure.repositories import WorkerRepository
    from src.modules.config.application.services import ConfigService
    s = setup
    asset = await _monitored_asset(s, storage)
    assert asset["monitoring_status"] == "Unconfirmed"
    async with AsyncSessionFactory() as db:
        job = await db.scalar(select(ConfigDelivery).where(ConfigDelivery.zone_id == s.places[0].zone.id)
                              .order_by(ConfigDelivery.version.desc()).limit(1))
        pushed = job.payload["config"]["assets"]
        assert [entry["asset_id"] for entry in pushed] == [asset["id"]]
        assert pushed[0]["camera_id"] == s.places[0].camera.public_id and pushed[0]["roi_fingerprint"]
        await db.execute(update(type(s.places[0].camera)).where(type(s.places[0].camera).id == s.places[0].camera.id)
                         .values(worker_id=s.worker.id))
        await db.commit()
        polled = await WorkerService(WorkerRepository(db)).get_worker_cameras(s.worker.id, db)
        assert polled[0]["zone_config"]["assets"] == pushed
        # A PPE threshold save must keep carrying the zone's assets.
        await ConfigService(db).update_zone_config(s.places[0].zone.public_id, s.enterprise.public_id,
                                                   {"helmet_threshold": 0.8}, s.users["admin"].public_id)
        latest = await db.scalar(select(ConfigDelivery).where(ConfigDelivery.zone_id == s.places[0].zone.id)
                                 .order_by(ConfigDelivery.version.desc()).limit(1))
        assert latest.payload["config"]["assets"] == pushed
    deleted = await s.client.delete(f"/api/v1/safety-assets/{asset['id']}", headers=headers(s))
    assert deleted.status_code == 200
    async with AsyncSessionFactory() as db:
        latest = await db.scalar(select(ConfigDelivery).where(ConfigDelivery.zone_id == s.places[0].zone.id)
                                 .order_by(ConfigDelivery.version.desc()).limit(1))
        assert latest.payload["config"]["assets"] == []


@needs_db
async def test_incidents_dedupe_alert_attach_evidence_and_clear(setup, storage):
    from src.shared.database.models import Alert, AssetIncident
    from src.shared.database.session import AsyncSessionFactory
    from src.shared.messaging.consumer import _route_event
    s = setup
    asset = await _monitored_asset(s, storage)
    first = _event(s, asset["id"])
    await _route_event("events.asset_area_changed", first)
    await _route_event("events.asset_area_changed", dict(first))      # broker redelivery
    await _route_event("events.asset_area_changed", _event(s, asset["id"]))  # flapping area
    async with AsyncSessionFactory() as db:
        incidents = list(await db.scalars(select(AssetIncident).where(AssetIncident.camera_id == s.places[0].camera.id)))
        assert len(incidents) == 2 and len({i.alert_id for i in incidents}) == 1
        alert = await db.scalar(select(Alert).where(Alert.id == incidents[0].alert_id))
        assert alert.alert_type == "SAFETY_ASSET_AREA_CHANGED" and alert.severity == "High"
    detail = await s.client.get(f"/api/v1/alerts/{alert.public_id}", headers=headers(s))
    assert detail.json()["data"]["safety_asset"]["asset_id"] == asset["id"]
    assert detail.json()["data"]["safety_asset"]["has_snapshot"]
    listed = await s.client.get("/api/v1/safety-assets", headers=headers(s))
    assert next(a for a in listed.json()["data"] if a["id"] == asset["id"])["open_incident"]["kind"] == "AREA_CHANGED"
    await _route_event("events.asset_restored", _event(s, asset["id"], snapshot_key=None))
    async with AsyncSessionFactory() as db:
        assert await db.scalar(select(func.count()).select_from(AssetIncident).where(
            AssetIncident.camera_id == s.places[0].camera.id, AssetIncident.cleared_at.is_(None))) == 0
        # Restoring the area does not close the human review.
        assert await db.scalar(select(Alert.status).where(Alert.id == alert.id)) == "Open"


@needs_db
async def test_evidence_key_outside_camera_prefix_and_foreign_asset_rejected(setup, storage):
    from src.shared.messaging.consumer import _route_event
    s = setup
    asset = await _monitored_asset(s, storage)
    with pytest.raises(ValueError):
        await _route_event("events.asset_area_changed", _event(s, asset["id"], snapshot_key="other-tenant/x.jpg"))
    with pytest.raises(ValueError):
        # The asset's camera is place 0; an event from place 1's camera must not touch it.
        await _route_event("events.asset_area_changed", _event(s, asset["id"], place=1))


@needs_db
async def test_maintenance_records_incident_without_alert(setup, storage):
    from src.shared.database.models import AssetIncident, Camera
    from src.shared.database.session import AsyncSessionFactory
    from src.shared.messaging.consumer import _route_event
    s = setup
    asset = await _monitored_asset(s, storage)
    async with AsyncSessionFactory() as db:
        await db.execute(update(Camera).where(Camera.id == s.places[0].camera.id).values(
            in_maintenance=True, maintenance_until=datetime.now(timezone.utc) + timedelta(hours=1)))
        await db.commit()
    await _route_event("events.asset_area_changed", _event(s, asset["id"]))
    async with AsyncSessionFactory() as db:
        incident = await db.scalar(select(AssetIncident).where(AssetIncident.camera_id == s.places[0].camera.id))
        assert incident is not None and incident.alert_id is None


@needs_db
async def test_status_telemetry_never_moves_backwards(setup, storage):
    from src.shared.messaging.consumer import _route_event
    s = setup
    asset = await _monitored_asset(s, storage)
    now = datetime.now(timezone.utc)
    body = {**_event(s, asset["id"]), "assets": [{"asset_id": asset["id"], "state": "Occluded", "similarity": None}]}
    await _route_event("events.asset_status_updated", {**body, "timestamp": now.isoformat()})
    older = {**body, "timestamp": (now - timedelta(minutes=1)).isoformat(),
             "assets": [{"asset_id": asset["id"], "state": "OK", "similarity": 0.9}]}
    await _route_event("events.asset_status_updated", older)
    current = (await s.client.get(f"/api/v1/safety-assets/{asset['id']}", headers=headers(s))).json()["data"]
    assert current["monitoring_status"] == "Occluded"
