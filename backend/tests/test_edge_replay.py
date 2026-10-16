"""Persisted edge replay against the real backend transaction boundary."""
import importlib.util
import json
from datetime import datetime, timedelta
from uuid import uuid4
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select, update

from src.shared.database.models import Alert, PPEViolation, CameraLease
from src.modules.worker.infrastructure.leases import CameraLeaseRepository
from src.shared.database.session import AsyncSessionFactory
from tests.test_review_integration import event, pytestmark as pytestmark, setup as setup


async def test_restarted_edge_replay_keeps_one_incident_before_evidence_upload(setup, tmp_path):
    spec = importlib.util.spec_from_file_location("edge_journal_under_test",
        Path(__file__).resolve().parents[2] / "ai-worker/src/events/journal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from src.shared.messaging.consumer import _route_event

    identity = {"worker_id": setup.worker.worker_id, "enterprise_id": setup.enterprise.public_id}
    body = event(setup)
    async with AsyncSessionFactory() as db:
        grant = (await CameraLeaseRepository(db).acquire(setup.enterprise.public_id,
            setup.worker.id, str(uuid4())))[body["camera_id"]]
        observed = datetime.fromisoformat(body["timestamp"])
        await db.execute(update(CameraLease).where(CameraLease.token == grant["token"]).values(
            started_at=observed - timedelta(seconds=10), expires_at=observed + timedelta(seconds=10)))
        await db.commit()
        await CameraLeaseRepository(db).acquire(setup.enterprise.public_id, setup.worker.id, str(uuid4()))
    body.update(worker_id=setup.worker.worker_id, camera_lease={**grant, "observed_at": body["timestamp"]})
    body["snapshot_key"] = f"{body['enterprise_id']}/{body['factory_id']}/{body['zone_id']}/{body['camera_id']}/{body['event_id']}.jpg"
    journal = module.EdgeJournal(tmp_path / "edge", identity, min_free_bytes=0)
    journal.enqueue("events.helmet_missing_detected", body, b"test-evidence-not-yet-uploaded")
    journal.close()
    journal = module.EdgeJournal(tmp_path / "edge", identity, min_free_bytes=0)
    try:
        row = journal.next_due("event")
        with patch("src.modules.realtime.manager.manager.broadcast", new=AsyncMock()):
            for _ in range(2):  # Delivery acknowledgment was lost before the local commit.
                await _route_event(row["routing_key"], json.loads(row["payload"]))
        async with AsyncSessionFactory() as db:
            violations = (await db.scalars(select(PPEViolation).where(
                PPEViolation.camera_id == setup.places[0].camera.id))).all()
            assert len(violations) == 1
            assert violations[0].snapshot_key == body["snapshot_key"]
            assert violations[0].created_at.isoformat() == body["timestamp"]
            assert await db.scalar(select(func.count()).select_from(Alert).where(
                Alert.camera_id == setup.places[0].camera.id)) == 1
        journal.succeeded(body["event_id"], "event")
        assert journal.stats()["events"] == 0 and journal.stats()["evidence"] == 1
        assert journal.next_due("evidence")["snapshot"] == b"test-evidence-not-yet-uploaded"
        journal.succeeded(body["event_id"], "evidence")
        assert journal.stats()["rows"] == 0
    finally:
        journal.close()
