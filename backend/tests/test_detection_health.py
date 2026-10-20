"""Current inference evidence, expiry, lease fencing and scoped gap counts."""
from datetime import timedelta
import os
from uuid import uuid4
from unittest.mock import Mock

import pytest
from sqlalchemy import event, func, update

from src.shared.database.models import AIWorker, Camera, CameraConfigApplication, CameraLease, ZoneConfig
from src.shared.database.session import AsyncSessionFactory, engine
from tests.test_config_delivery import ack, make_ack, save
from tests.test_review_integration import headers, setup as setup

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL and Redis")


async def health(s, caller="admin", **params):
    return await s.client.get("/api/v1/analytics/detection-health", headers=headers(s, caller), params=params)


async def prepared(s, monkeypatch, age=0.0):
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    item["detection_health"] = {"inference_age_seconds": age}
    response = await ack(s, auth, item)
    assert response.json()["data"]["accepted"] == 1
    return auth, item


async def test_current_inference_is_distinct_from_camera_activation_and_worker_heartbeat(setup, monkeypatch):
    s = setup
    assert (await health(s)).json()["data"]["summary"]["states"] == {"Unassigned": 2}
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    await ack(s, auth, item)  # Old workers can confirm policy, not detection.
    assert (await health(s)).json()["data"]["summary"]["states"]["TelemetryMissing"] == 1
    item["detection_health"] = {"inference_age_seconds": None}
    await ack(s, auth, item)
    assert (await health(s)).json()["data"]["summary"]["states"]["InferenceStale"] == 1
    item["detection_health"]["inference_age_seconds"] = 0.0
    await ack(s, auth, item)
    result = (await health(s, "manager")).json()["data"]
    assert result["summary"]["status"] == "RecentInferenceObserved"
    assert result["summary"]["detecting_cameras"] == 1
    assert "rtsp" not in str(result) and "lease_token" not in str(result)


@pytest.mark.parametrize("fault,expected", [("heartbeat", "WorkerUnavailable"), ("lease", "LeaseExpired"),
    ("telemetry", "TelemetryMissing"), ("inference", "InferenceStale"), ("config", "ConfigPending")])
async def test_health_deteriorates_without_a_broker_offline_event(setup, monkeypatch, fault, expected):
    s = setup
    await prepared(s, monkeypatch)
    async with AsyncSessionFactory() as db:
        past = func.now() - timedelta(seconds=61)
        if fault == "heartbeat":
            await db.execute(update(AIWorker).where(AIWorker.id == s.worker.id).values(last_heartbeat=past))
        elif fault == "lease":
            await db.execute(update(CameraLease).where(CameraLease.worker_id == s.worker.id).values(expires_at=past))
        elif fault == "config":
            await db.execute(update(ZoneConfig).where(ZoneConfig.id == s.places[0].config.id).values(version=3))
        else:
            field = "health_reported_at" if fault == "telemetry" else "last_inference_at"
            await db.execute(update(CameraConfigApplication).where(CameraConfigApplication.camera_id == s.places[0].camera.id)
                             .values(**{field: past}))
        await db.commit()
    result = (await health(s, "manager")).json()["data"]["summary"]
    assert result["status"] == "DetectionGap" and result["states"] == {expected: 1}


async def test_offline_and_recovery_follow_successful_inference_reports(setup, monkeypatch):
    s = setup
    auth, item = await prepared(s, monkeypatch, age=None)
    async with AsyncSessionFactory() as db:
        await db.execute(update(Camera).where(Camera.id == s.places[0].camera.id).values(status="Offline"))
        await db.commit()
    assert (await health(s, "manager")).json()["data"]["summary"]["states"] == {"StreamOffline": 1}
    item["detection_health"]["inference_age_seconds"] = 0.0
    await ack(s, auth, item)
    assert (await health(s, "manager")).json()["data"]["summary"]["status"] == "RecentInferenceObserved"
    item["lease_token"] = str(uuid4())
    item["detection_health"]["inference_age_seconds"] = None
    assert (await ack(s, auth, item)).json()["data"]["rejected"] == 1
    assert (await health(s, "manager")).json()["data"]["summary"]["detecting_cameras"] == 1


async def test_paused_maintenance_and_empty_scopes_never_appear_as_healthy_detection(setup):
    s = setup
    async with AsyncSessionFactory() as db:
        await db.execute(update(Camera).where(Camera.id == s.places[0].camera.id).values(status="Inactive"))
        await db.execute(update(Camera).where(Camera.id == s.places[1].camera.id).values(in_maintenance=True))
        await db.commit()
    result = (await health(s)).json()["data"]["summary"]
    assert result["expected_cameras"] == 0 and result["paused_cameras"] == 2
    assert result["status"] == "NoMonitoringExpected"
    async with AsyncSessionFactory() as db:
        await db.execute(update(Camera).where(Camera.id == s.places[1].camera.id)
            .values(maintenance_until=func.now() - timedelta(seconds=1)))
        await db.commit()
    assert (await health(s)).json()["data"]["summary"]["gap_cameras"] == 1


async def test_scope_filter_pagination_and_constant_query_count(setup, monkeypatch):
    s = setup
    await prepared(s, monkeypatch)
    for caller, expected in [("admin", 2), ("manager", 1), ("viewer", 1), ("foreign", 1)]:
        response = (await health(s, caller, page_size=1)).json()
        assert response["data"]["summary"]["total_cameras"] == expected
        assert len(response["data"]["cameras"]) == 1
    assert (await health(s, "manager", zone_id=s.places[1].zone.public_id)).status_code == 404
    filtered = (await health(s, problems_only=True)).json()
    assert filtered["meta"]["total"] == 1 and filtered["data"]["cameras"][0]["state"] == "Unassigned"
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)
    counts = []
    from src.modules.analytics.application.detection_health import detection_health
    from src.shared.security.scope import ScopeFilter
    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        for size in (1, 100):
            async with AsyncSessionFactory() as db:
                statements.clear()
                await detection_health(db, s.enterprise.public_id, ScopeFilter(unrestricted=True), page_size=size)
                counts.append(len(statements))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert counts == [4, 4]


@pytest.mark.parametrize("age", [-1, 31, True, "0", float("inf")])
async def test_invalid_health_samples_cannot_create_fresh_detection(setup, monkeypatch, age):
    import json
    s = setup
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    item["detection_health"] = {"inference_age_seconds": age}
    # Encode infinity explicitly so server-side validation, rather than the
    # client's JSON serializer, rejects it.
    response = await s.client.post(f"/api/v1/workers/{s.worker.worker_id}/config-applied", headers={**auth, "Content-Type": "application/json"},
        content=json.dumps({"applications": [item]}))
    assert response.status_code == 422


async def test_no_alerts_never_produces_a_perfect_safety_or_compliance_score(setup, monkeypatch):
    s = setup
    await prepared(s, monkeypatch)
    result = (await s.client.get("/api/v1/analytics/safety-score", headers=headers(s))).json()["data"]
    assert result["score"] is None and result["reason"] == "historical_monitoring_coverage_not_measured"
    assert result["alerts_by_severity"] == {}
    compliance = (await s.client.get("/api/v1/analytics/compliance", headers=headers(s))).json()["data"]
    assert compliance["resolution_rate_pct"] is None and compliance["sla_compliance_pct"] is None


async def test_legacy_acknowledgements_never_refresh_inference_or_carry_it_into_new_policy(setup, monkeypatch):
    s = setup
    auth, item = await prepared(s, monkeypatch)
    async with AsyncSessionFactory() as db:
        await db.execute(update(CameraConfigApplication).where(CameraConfigApplication.camera_id == s.places[0].camera.id)
            .values(health_reported_at=func.now() - timedelta(seconds=61)))
        await db.commit()
    item.pop("detection_health")
    await ack(s, auth, item)
    assert (await health(s, "manager")).json()["data"]["summary"]["states"] == {"TelemetryMissing": 1}
    await save(s)
    item["version"] = 3
    await ack(s, auth, item)
    result = (await health(s, "manager")).json()["data"]
    assert result["cameras"][0]["last_inference_at"] is None
    assert result["summary"]["states"] == {"TelemetryMissing": 1}


async def test_empty_service_scope_returns_no_cameras_or_detection_claim(setup):
    from src.modules.analytics.application.detection_health import detection_health
    from src.shared.security.scope import ScopeFilter
    async with AsyncSessionFactory() as db:
        result = await detection_health(db, setup.enterprise.public_id, ScopeFilter(unrestricted=False))
    assert result["cameras"] == [] and result["summary"]["total_cameras"] == 0
    assert result["summary"]["status"] == "NoMonitoringExpected"


async def test_database_wait_cannot_make_an_old_health_sample_look_current(setup, monkeypatch):
    s = setup
    await save(s)
    auth, item = await make_ack(s, monkeypatch)
    item["detection_health"] = {"inference_age_seconds": 0.0}
    monkeypatch.setattr("src.modules.config.application.application_status.monotonic", Mock(side_effect=[0, 61]))
    assert (await ack(s, auth, item)).json()["data"]["accepted"] == 1
    result = (await health(s, "manager")).json()["data"]
    assert result["summary"]["states"] == {"TelemetryMissing": 1}
