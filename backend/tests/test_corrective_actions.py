"""Real PostgreSQL corrective workflows, races and authenticated photo access."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
from unittest.mock import AsyncMock
from uuid import uuid4

from PIL import Image
import pytest
from sqlalchemy import event, func, select, update

from src.modules.alerts.application import corrective
from src.shared.database.models import Alert, AlertHistory, CorrectiveEvidence, Role, User, UserRole
from src.shared.database.session import AsyncSessionFactory
from tests.test_review_integration import headers, make_review_incident, setup as setup

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires disposable PostgreSQL and Redis")


def photo():
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
def storage(monkeypatch):
    objects = {}
    async def store(key, content, content_type):
        objects[key] = content
    monkeypatch.setattr(corrective, "store_photo", AsyncMock(side_effect=store))
    monkeypatch.setattr(corrective, "read_photo", AsyncMock(side_effect=lambda key: objects[key]))
    return objects


async def save_plan(s, alert, revision=0, caller="admin", **changes):
    body = {"assigned_to": s.users["manager"].public_id, "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "description": "  Replace the missing helmet and check the work area.  ", "expected_revision": revision, **changes}
    return await s.client.put(f"/api/v1/alerts/{alert.public_id}/corrective-action", headers=headers(s, caller), json=body)


async def action(s, alert, caller="admin"):
    return await s.client.get(f"/api/v1/alerts/{alert.public_id}/corrective-action", headers=headers(s, caller))


async def upload(s, alert, revision, upload_id=None, content=None, caller="admin"):
    return await s.client.post(f"/api/v1/alerts/{alert.public_id}/corrective-action/evidence", headers=headers(s, caller),
        data={"expected_revision": str(revision), "upload_id": upload_id or str(uuid4())},
        files={"file": ("corrected.png", photo() if content is None else content, "image/png")})


async def complete(s, alert, revision, caller="admin"):
    return await s.client.post(f"/api/v1/alerts/{alert.public_id}/corrective-action/complete", headers=headers(s, caller),
        json={"expected_revision": revision, "note": "  Helmet replaced and supervisor checked the area.  "})


async def test_plan_photo_completion_and_final_review_have_atomic_history(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    response = await save_plan(s, alert)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["description"].startswith("Replace")
    assert (await complete(s, alert, 1)).status_code == 422
    url = f"/api/v1/alerts/{alert.public_id}"
    assert (await s.client.patch(url + "/resolve", headers=headers(s), json={"note": "Closing"})).status_code == 409
    attached = await upload(s, alert, 1)
    assert attached.status_code == 200, attached.text
    evidence = attached.json()["data"]["evidence"][0]
    assert evidence["sha256"] == hashlib.sha256(photo()).hexdigest()
    assert (await complete(s, alert, 2, "manager")).status_code == 200
    assert (await s.client.patch(url + "/resolve", headers=headers(s), json={})).status_code == 422
    assert (await s.client.patch(url + "/resolve", headers=headers(s), json={"note": "Reviewed proof and closed."})).status_code == 200
    detail = (await s.client.get(url, headers=headers(s))).json()["data"]
    assert [item["event_type"] for item in detail["review_history"]] == ["ACTION_PLANNED", "EVIDENCE_ADDED", "ACTION_COMPLETED", "STATUS_CHANGED"]
    assert detail["review_history"][2]["comment"] == "Helmet replaced and supervisor checked the area."
    assert (await action(s, alert)).json()["data"]["status"] == "Completed"


async def test_evidence_download_rechecks_scope_and_integrity(setup, storage, monkeypatch):
    s = setup
    alert, _ = await make_review_incident(s)
    other_alert, _ = await make_review_incident(s, 1)
    await save_plan(s, alert)
    evidence = (await upload(s, alert, 1)).json()["data"]["evidence"][0]
    path = f"/api/v1/alerts/{alert.public_id}/corrective-action/evidence/{evidence['id']}"
    for caller in ("admin", "manager", "viewer"):
        response = await s.client.get(path, headers=headers(s, caller))
        assert response.status_code == 200 and response.content == photo()
        assert response.headers["cache-control"] == "no-store" and response.headers["content-type"] == "image/png"
    assert (await s.client.get(path, headers=headers(s, "foreign"))).status_code == 404
    assert (await s.client.get(path.replace(alert.public_id, other_alert.public_id), headers=headers(s))).status_code == 404
    monkeypatch.setattr(corrective, "read_photo", AsyncMock(return_value=b"damaged"))
    assert (await s.client.get(path, headers=headers(s))).status_code == 503


async def test_upload_retries_are_idempotent_and_never_rewrite_committed_bytes(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    await save_plan(s, alert)
    key = str(uuid4())
    first = await upload(s, alert, 1, key)
    second = await upload(s, alert, 1, key)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["revision"] == second.json()["data"]["revision"] == 2
    assert len(storage) == 1
    assert (await upload(s, alert, 2, key, b"different bytes")).status_code == 409
    assert len(storage) == 1


async def test_replanning_invalidates_prior_completion_and_photo_for_new_action(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    await save_plan(s, alert)
    await upload(s, alert, 1)
    await complete(s, alert, 2)
    replanned = await save_plan(s, alert, revision=3, description="Recheck the new work position")
    data = replanned.json()["data"]
    assert data["completed_at"] is None and data["plan_version"] == 2 and not data["evidence"][0]["current_plan"]
    assert (await complete(s, alert, 4)).status_code == 422


async def test_candidates_only_include_active_reviewers_who_can_access_incident(setup):
    s = setup
    alert, _ = await make_review_incident(s)
    response = await s.client.get(f"/api/v1/alerts/{alert.public_id}/assignees?page_size=1", headers=headers(s))
    assert response.status_code == 200 and response.json()["meta"]["total"] == 2
    assert len(response.json()["data"]) == 1 and "email" not in response.text
    assert (await save_plan(s, alert, assigned_to=s.users["viewer"].public_id)).status_code == 422
    assert (await save_plan(s, alert, assigned_to=s.users["foreign"].public_id)).status_code in (404, 422)
    async with AsyncSessionFactory() as db:
        await db.execute(update(User).where(User.id == s.users["manager"].id).values(factory_id=s.places[1].factory.id))
        await db.commit()
    assert (await save_plan(s, alert)).status_code == 422


async def test_role_scope_and_due_date_validation_protect_plan(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    foreign, _ = await make_review_incident(s, 2)
    hidden, _ = await make_review_incident(s, 1)
    assert (await action(s, foreign)).status_code == 404
    assert (await action(s, hidden, "manager")).status_code == 404
    assert (await save_plan(s, alert, caller="viewer")).status_code == 403
    assert (await upload(s, alert, 0, caller="viewer")).status_code == 403
    assert (await complete(s, alert, 0, "viewer")).status_code == 403
    assert (await save_plan(s, alert, due_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())).status_code == 422
    assert (await save_plan(s, alert, due_at="2026-12-01T12:00:00")).status_code == 422
    assert (await save_plan(s, alert, description="  ")).status_code == 422
    assert (await action(s, alert)).json()["data"]["revision"] == 0


@pytest.mark.parametrize("content,expected", [(b"not a photo", 422), (b"x" * (5 * 1024 * 1024 + 1), 422), (b"x" * (7 * 1024 * 1024), 413)])
async def test_invalid_or_oversized_uploads_never_reach_storage(setup, storage, content, expected):
    alert, _ = await make_review_incident(setup)
    await save_plan(setup, alert)
    response = await upload(setup, alert, 1, content=content)
    assert response.status_code == expected, response.text
    assert storage == {}


async def test_conflicting_plan_and_resolution_cannot_both_commit(setup):
    s = setup
    alert, _ = await make_review_incident(s)
    plan, closure = await asyncio.gather(save_plan(s, alert),
        s.client.patch(f"/api/v1/alerts/{alert.public_id}/resolve", headers=headers(s), json={"note": "Final review"}))
    assert sorted([plan.status_code, closure.status_code]) == [200, 409]


async def test_stale_revision_and_legacy_assignment_cannot_bypass_action_gate(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    await save_plan(s, alert)
    assert (await save_plan(s, alert, revision=0)).status_code == 409
    await upload(s, alert, 1)
    await complete(s, alert, 2)
    same = await s.client.patch(f"/api/v1/alerts/{alert.public_id}/assign", headers=headers(s), json={"user_id": s.users["manager"].public_id})
    assert same.status_code == 200 and (await action(s, alert)).json()["data"]["completed_at"] is not None
    response = await s.client.patch(f"/api/v1/alerts/{alert.public_id}/assign", headers=headers(s), json={"user_id": s.users["admin"].public_id})
    assert response.status_code == 200 and response.json()["data"]["action_completed_at"] is None
    current = (await action(s, alert)).json()["data"]
    assert current["completed_at"] is None and current["plan_version"] == 2
    assert (await s.client.patch(f"/api/v1/alerts/{alert.public_id}/resolve", headers=headers(s), json={"note": "Attempt"})).status_code == 409


async def test_false_positive_cancels_planned_action_and_closed_incidents_are_immutable(setup):
    s = setup
    alert, _ = await make_review_incident(s)
    await save_plan(s, alert)
    assert (await s.client.patch(f"/api/v1/alerts/{alert.public_id}/false-positive", headers=headers(s), json={"reason": "Confirmed false detection"})).status_code == 200
    assert (await action(s, alert)).json()["data"]["status"] == "Cancelled"
    assert (await save_plan(s, alert, revision=1)).status_code == 409
    assert (await s.client.patch(f"/api/v1/alerts/{alert.public_id}/assign", headers=headers(s), json={"user_id": s.users["admin"].public_id})).status_code == 409


async def test_history_failure_rolls_back_plan_and_revision(setup):
    alert, _ = await make_review_incident(setup)
    def fail(*args):
        raise RuntimeError("injected history failure")
    event.listen(AlertHistory, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected history"):
            await save_plan(setup, alert)
    finally:
        event.remove(AlertHistory, "before_insert", fail)
    async with AsyncSessionFactory() as db:
        row = await db.get(Alert, alert.id)
        assert row.action_description is None and row.action_revision == 0
        assert await db.scalar(select(func.count()).select_from(AlertHistory).where(AlertHistory.alert_id == alert.id)) == 0
        assert await db.scalar(select(func.count()).select_from(CorrectiveEvidence).where(CorrectiveEvidence.alert_id == alert.id)) == 0


async def test_overdue_filter_excludes_completed_closed_and_foreign_actions(setup, storage):
    s = setup
    own, _ = await make_review_incident(s)
    foreign, _ = await make_review_incident(s, 2)
    await save_plan(s, own)
    async with AsyncSessionFactory() as db:
        await db.execute(update(Alert).where(Alert.id.in_([own.id, foreign.id])).values(
            action_description="Due action", action_due_at=datetime.now(timezone.utc) - timedelta(days=1)))
        await db.commit()
    response = await s.client.get("/api/v1/alerts?corrective_overdue=true", headers=headers(s))
    assert response.status_code == 200 and response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["id"] == own.public_id
    assert (await action(s, own)).json()["data"]["overdue"] is True
    await upload(s, own, 1)
    await complete(s, own, 2)
    assert (await s.client.get("/api/v1/alerts?corrective_overdue=true", headers=headers(s))).json()["data"] == []


async def test_photo_transfers_use_real_minio_sdk_against_local_s3_fixture(setup, monkeypatch):
    """Transport fixture does not validate real MinIO authentication or TLS."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from minio import Minio
    objects = {}
    class S3Fixture(BaseHTTPRequestHandler):
        def do_PUT(self):
            data = self.rfile.read(int(self.headers["Content-Length"]))
            objects[self.path] = data
            self.send_response(200)
            self.send_header("ETag", '"test-etag"')
            self.send_header("Content-Length", "0")
            self.end_headers()
        def do_GET(self):
            data = objects[self.path]
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), S3Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(corrective, "photo_client", lambda: Minio(f"127.0.0.1:{server.server_port}",
        access_key="test-only", secret_key="test-only-secret", secure=False, region="us-east-1"))
    try:
        alert, _ = await make_review_incident(setup)
        await save_plan(setup, alert)
        response = await upload(setup, alert, 1)
        assert response.status_code == 200, response.text
        evidence_id = response.json()["data"]["evidence"][0]["id"]
        download = await setup.client.get(f"/api/v1/alerts/{alert.public_id}/corrective-action/evidence/{evidence_id}", headers=headers(setup, "viewer"))
        assert download.status_code == 200 and download.content == photo()
        assert next(iter(objects.values())) == photo()
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)


async def test_only_assigned_safety_officer_or_scoped_manager_can_complete(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    async with AsyncSessionFactory() as db:
        role = await db.scalar(select(Role).where(Role.code == "SAFETY_OFFICER"))
        db.add(UserRole(user_public_id=s.users["viewer"].public_id, role_public_id=role.public_id))
        await db.commit()
    await save_plan(s, alert)
    await upload(s, alert, 1)
    assert (await complete(s, alert, 2, "viewer")).status_code == 403
    await save_plan(s, alert, revision=2, assigned_to=s.users["viewer"].public_id)
    await upload(s, alert, 3)
    assert (await complete(s, alert, 4, "viewer")).status_code == 200


async def test_storage_outage_leaves_action_and_history_unchanged(setup, monkeypatch):
    from unittest.mock import Mock
    s = setup
    alert, _ = await make_review_incident(s)
    await save_plan(s, alert)
    monkeypatch.setattr(corrective, "photo_client", lambda: Mock(put_object=Mock(side_effect=OSError("test outage"))))
    assert (await upload(s, alert, 1)).status_code == 503
    current = (await action(s, alert)).json()["data"]
    assert current["revision"] == 1 and current["evidence"] == []


async def test_photo_quota_preserves_a_completable_plan_and_rejects_more_writes(setup, storage):
    s = setup
    alert, _ = await make_review_incident(s)
    await save_plan(s, alert)
    async with AsyncSessionFactory() as db:
        db.add_all([CorrectiveEvidence(enterprise_id=s.enterprise.id, alert_id=alert.id, plan_version=1,
            object_key=f"test-only/{uuid4()}", filename="quota.png", content_type="image/png", size_bytes=len(photo()),
            sha256=hashlib.sha256(photo()).hexdigest()) for _ in range(50)])
        await db.commit()
    assert (await upload(s, alert, 1)).status_code == 422 and storage == {}
    assert (await save_plan(s, alert, revision=1)).status_code == 422
    assert (await complete(s, alert, 1)).status_code == 200
    assert (await s.client.patch(f"/api/v1/alerts/{alert.public_id}/assign", headers=headers(s),
        json={"user_id": s.users["admin"].public_id})).status_code == 422
    current = (await action(s, alert)).json()["data"]
    assert current["plan_version"] == 1 and current["completed_at"] is not None
