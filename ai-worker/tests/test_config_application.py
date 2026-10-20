"""Policy installation reports, missed-push repair and monotonic hot reload."""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from src.config.application_reporter import report_applications
from src.config.ownership import bind_assignments, lease_clock
from src.config.zone_sync import ZoneConfigSync
from src.pipeline.camera_worker import CameraWorker
from tests.test_worker_leases import camera_grant


def worker():
    lease = bind_assignments([camera_grant()], lease_clock())[0]["lease"]
    return CameraWorker(str(uuid4()), "rtsp://example.invalid/feed", {"version": 2, "required_ppe_types": ["helmet"]},
                        str(uuid4()), str(uuid4()), str(uuid4()), Mock(), lease=lease)


def test_duplicate_stale_foreign_and_expired_pushes_do_not_replace_policy():
    w = worker()
    sync = ZoneConfigSync([w])
    body = {"enterprise_id": w.enterprise_id, "zone_id": w.zone_id,
            "config": {"version": 3, "required_ppe_types": ["vest"]}}
    sync._apply_zone_config(body)
    assert w.zone_config["version"] == 3 and w.zone_config["ppe_required"] == ["vest"]
    revision = w._policy_revision
    for bad in [body, {**body, "config": {"version": 2}}, {**body, "enterprise_id": str(uuid4()), "config": {"version": 4}},
                {**body, "zone_id": str(uuid4()), "config": {"version": 4}}]:
        sync._apply_zone_config(bad)
    assert w._policy_revision == revision
    w.lease["deadline"] = lease_clock() - 1
    sync._apply_zone_config({**body, "config": {"version": 4}})
    assert w.zone_config["version"] == 3


@pytest.mark.asyncio
async def test_push_reports_after_installation_and_never_on_install_failure(monkeypatch):
    w = worker()
    versions = []
    async def reported(workers):
        versions.append(workers[0].zone_config["version"])
    @asynccontextmanager
    async def processed(**kwargs):
        yield
    body = {"enterprise_id": w.enterprise_id, "zone_id": w.zone_id,
            "config": {"version": 3, "required_ppe_types": ["vest"]}}
    message = SimpleNamespace(body=json.dumps(body).encode(), routing_key="config.zone_config_updated", process=processed)
    sync = ZoneConfigSync([w], report_applications=reported)
    await sync._on_message(message)
    assert versions == [3]
    body["config"]["version"] = 4
    message.body = json.dumps(body).encode()
    monkeypatch.setattr(w, "apply_zone_config", Mock(side_effect=RuntimeError("install failed")))
    with pytest.raises(RuntimeError, match="install failed"):
        await sync._on_message(message)
    assert versions == [3]


@pytest.mark.asyncio
async def test_http_snapshot_cannot_undo_a_newer_push_and_next_poll_repairs_missed_push():
    from src.main import reconcile_cameras
    w = worker()
    w.apply_zone_config({"version": 4, "required_ppe_types": ["vest"]})
    task = asyncio.create_task(asyncio.Event().wait())
    workers, tasks = [w], {w.camera_id: task}
    snapshot = {"camera_id": w.camera_id, "zone_id": w.zone_id, "lease": w.lease,
                "rtsp_url": w.rtsp_url, "zone_config": {"version": 3, "required_ppe_types": ["helmet"]}}
    try:
        await reconcile_cameras(workers, tasks, None, [snapshot])
        assert w.zone_config["version"] == 4 and w.zone_config["ppe_required"] == ["vest"]
        snapshot["zone_config"] = {"version": 5, "required_ppe_types": ["helmet", "vest"]}
        await reconcile_cameras(workers, tasks, None, [snapshot])
        assert w.zone_config["version"] == 5 and w.zone_config["ppe_required"] == ["helmet", "vest"]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_report_failure_is_retried_and_expired_workers_are_excluded(monkeypatch):
    w, expired = worker(), worker()
    expired.lease["deadline"] = lease_clock() - 1
    response = httpx.Response(200, json={"data": {"accepted": 1, "rejected": 0}}, request=httpx.Request("POST", "https://test"))
    post = AsyncMock(side_effect=[httpx.ConnectError("unavailable"), response])
    client = AsyncMock()
    client.__aenter__.return_value = SimpleNamespace(post=post)
    monkeypatch.setattr("src.config.application_reporter.httpx.AsyncClient", lambda **kw: client)
    await report_applications([w, expired])  # Must not stop detection.
    await report_applications([w, expired])
    assert post.await_count == 2
    assert post.await_args.kwargs["json"] == {"applications": [{"camera_id": w.camera_id, "zone_id": w.zone_id,
        "lease_token": w.lease["token"], "version": 2, "detection_health": {"inference_age_seconds": None}}]}
    await report_applications([expired])
    assert post.await_count == 2


@pytest.mark.asyncio
async def test_reporting_batches_bound_request_size(monkeypatch):
    workers = [worker() for _ in range(201)]
    response = httpx.Response(200, json={"data": {"accepted": 1, "rejected": 0}}, request=httpx.Request("POST", "https://test"))
    post = AsyncMock(return_value=response)
    client = AsyncMock()
    client.__aenter__.return_value = SimpleNamespace(post=post)
    monkeypatch.setattr("src.config.application_reporter.httpx.AsyncClient", lambda **kw: client)
    await report_applications(workers)
    assert [len(call.kwargs["json"]["applications"]) for call in post.await_args_list] == [200, 1]
